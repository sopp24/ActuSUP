#!/usr/bin/env python3
"""Collecte des flux RSS de médias francophones et génération de data/news.json."""
from __future__ import annotations
import hashlib
import json
import re
import time
import html
import math
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import requests

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "news.json"
MAX_PER_SOURCE = 25
MAX_TOTAL = 300
FEATURED_LIMIT = 20
FEATURED_DAYS = 30
TIMEOUT = 20
USER_AGENT = "ActuSUP-NewsReader/1.0 (+https://github.com/; educational project)"

# Les URL de flux peuvent évoluer ; une source en erreur n'empêche pas les autres de fonctionner.
FEEDS = [
    # Médias généralistes et information continue
    {"name": "Franceinfo (TV)", "url": "https://www.francetvinfo.fr/titres.rss"},
    {"name": "France 24", "url": "https://www.france24.com/fr/rss"},
    {"name": "RFI", "url": "https://www.rfi.fr/fr/rss"},
    {"name": "Le Monde", "url": "https://www.lemonde.fr/rss/une.xml"},
    {"name": "Le Figaro", "url": "https://www.lefigaro.fr/rss/figaro_actualites.xml"},
    {"name": "BFMTV", "url": "https://www.bfmtv.com/rss/news-24-7/"},
    {"name": "20 Minutes", "url": "https://www.20minutes.fr/feeds/rss-une.xml"},
    {"name": "Actu.fr", "url": "https://actu.fr/rss.xml"},
    {"name": "Courrier International", "url": "https://www.courrierinternational.com/feed/all/rss.xml"},
    {"name": "Euronews", "url": "https://fr.euronews.com/rss"},
    {"name": "La Croix", "url": "https://www.la-croix.com/feeds/rss/site.xml"},
    {"name": "Libération", "url": "https://www.liberation.fr/arc/outboundfeeds/rss-all/?outputType=xml"},
    {"name": "Les Échos", "url": "https://www.lesechos.fr/rss/rss_une.xml"},
    {"name": "Ouest-France", "url": "https://www.ouest-france.fr/rss-en-continu.xml"},
    {"name": "L'Opinion", "url": "https://www.lopinion.fr/index.rss"},
    {"name": "L'Humanité", "url": "https://www.humanite.fr/feed"},
    {"name": "Sud Ouest", "url": "https://www.sudouest.fr/essentiel/rss.xml"},
    {"name": "La Voix du Nord", "url": "https://www.lavoixdunord.fr/rss.xml"},
    {"name": "Le Dauphiné Libéré", "url": "https://www.ledauphine.com/rss"},
    {"name": "La Dépêche du Midi", "url": "https://www.ladepeche.fr/rss.xml"},
    {"name": "Midi Libre", "url": "https://www.midilibre.fr/rss.xml"},
    {"name": "Le Point", "url": "https://www.lepoint.fr/24h-infos/rss.xml"},
    {"name": "L'Obs", "url": "https://www.nouvelobs.com/rss.xml"},
    {"name": "L'Express", "url": "https://www.lexpress.fr/arc/outboundfeeds/rss/alaune.xml"},
    {"name": "Le JDD", "url": "https://www.lejdd.fr/rss.xml"},
    {"name": "Alternatives économiques", "url": "https://www.alternatives-economiques.fr/rss.xml"},
    {"name": "Paris Match", "url": "https://www.parismatch.com/rss.xml"},
    {"name": "Valeurs actuelles", "url": "https://www.valeursactuelles.com/feed?post_type=post"},
    {"name": "TF1 Info (TF1 / LCI)", "url": "https://www.tf1info.fr/feeds/rss-une.xml"},
    {"name": "CNews", "url": "https://www.cnews.fr/rss.xml"},
    {"name": "France Info (Radio)", "url": "https://www.franceinfo.fr/titres.rss"},
    {"name": "France Inter", "url": "https://www.radiofrance.fr/franceinter/rss"},
    {"name": "RMC", "url": "https://rmc.bfmtv.com/rss/actualites/"},
    {"name": "France Culture", "url": "https://www.radiofrance.fr/franceculture/rss"},
    {"name": "Mediapart", "url": "https://www.mediapart.fr/articles/feed"},
    {"name": "Konbini", "url": "https://www.konbini.com/fr/feed/"},
    {"name": "Public Sénat", "url": "https://www.publicsenat.fr/rss"},
    {"name": "LCP", "url": "https://lcp.fr/rss.xml"},

    # Presse et médias spécialisés : communication, publicité, médias et création
    {"name": "CB News", "url": "https://www.cbnews.fr/rss.xml"},
    {"name": "Creapills", "url": "https://creapills.com/feed"},
    {"name": "INA – La Revue des médias", "url": "https://larevuedesmedias.ina.fr/rss/all"},

    # Presse spécialisée : numérique, sciences, environnement et culture
    {"name": "Next.ink", "url": "https://next.ink/feed/"},
    {"name": "Le Monde Informatique", "url": "https://www.lemondeinformatique.fr/flux-rss/thematique/toutes-les-actualites/rss.xml"},
    {"name": "Futura", "url": "https://www.futura-sciences.com/rss/actualites.xml"},
    {"name": "Reporterre", "url": "https://reporterre.net/spip.php?page=backend-simple"},
    {"name": "Télérama", "url": "https://www.telerama.fr/rss/latest-articles.xml"},
]

CATEGORY_RULES = [
    ("Médias & communication", ["communication", "publicité", "publicitaire", "média", "medias", "journaliste", "journalisme", "réseaux sociaux", "influenceur", "influenceuse", "tiktok", "instagram", "youtube", "meta", "marketing", "marque", "audiovisuel", "désinformation", "fake news", "plateforme numérique"]),
    ("Politique", ["président", "gouvernement", "ministre", "assemblée nationale", "sénat", "député", "élection", "élections", "parlement", "parti politique", "elysée", "élysée", "loi", "vote", "maire", "politique"]),
    ("Économie", ["économie", "économique", "inflation", "emploi", "emplois", "chômage", "entreprise", "entreprises", "bourse", "banque", "budget", "croissance", "prix", "carburant", "pouvoir d'achat", "consommation", "commerce", "industrie", "impôt", "taxe", "euro"]),
    ("Société", ["société", "éducation", "école", "étudiant", "étudiants", "santé", "hôpital", "justice", "police", "violence", "logement", "famille", "retraite", "manifestation", "social", "inégalité", "immigration"]),
    ("Sciences & tech", ["science", "scientifique", "recherche", "intelligence artificielle", " ia ", "technologie", "numérique", "cyber", "cybersécurité", "espace", "nasa", "robot", "découverte", "médecine", "vaccin", "santé numérique"]),
    ("Culture", ["culture", "cinéma", "film", "série", "musique", "livre", "roman", "littérature", "exposition", "musée", "théâtre", "artiste", "festival", "goncourt", "prix littéraire", "jeu vidéo"]),
    ("Sport", ["sport", "sports", "football", "rugby", "tennis", "basket", "olympique", "olympisme", "formule 1", "f1", "tour de france", "ligue 1", "championnat", "match", "athlète"]),
    ("Environnement", ["climat", "environnement", "écologie", "écologique", "biodiversité", "pollution", "réchauffement", "énergie", "énergies", "sécheresse", "inondation", "forêt", "incendie", "transition énergétique"]),
    ("International", ["international", "monde", "ukraine", "russie", "états-unis", "états unis", "chine", "iran", "israël", "gaza", "palestine", "onu", "otan", "afrique", "europe", "union européenne", "guerre", "diplomatie", "brésil"]),
]

# Normalisation commune : les mots-clés doivent correspondre à des mots entiers,
# pas à de simples sous-chaînes (ex. « loi » ne doit pas classer « emploi » en politique).
def normalize_keyword_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
    tokens = re.sub(r"[^a-z0-9]+", " ", normalized).split()
    # Réduire quelques pluriels français réguliers sans confondre des sous-chaînes.
    singularized = []
    for token in tokens:
        if len(token) > 5 and token.endswith("eaux"):
            token = token[:-1]  # bureaux → bureau, nouveaux → nouveau
        elif len(token) > 4 and token.endswith("aux"):
            token = token[:-3] + "al"  # sociaux → social, nationaux → national
        elif len(token) > 4 and token.endswith("s"):
            token = token[:-1]
        singularized.append(token)
    return " ".join(singularized)

NORMALIZED_CATEGORY_RULES = tuple(
    (category, tuple(normalize_keyword_text(keyword) for keyword in keywords))
    for category, keywords in CATEGORY_RULES
)

# Angles éditoriaux adaptés à chaque actualité à partir du titre et du résumé RSS.
# Les règles restent déterministes : aucune API d'IA ni clé secrète n'est nécessaire.
ARTICLE_ANGLE_RULES = [
    (("scandale", "controverse", "polémique", "boycott", "rappel de produit", "plainte contre", "mise en cause", "crise de réputation"),
     "Cette controverse ou mise en cause se joue aussi sur le terrain de la confiance. Pour les communicants, le travail consiste à distinguer les faits confirmés des réactions, préparer une réponse vérifiable et éviter une prise de parole défensive qui aggraverait la crise."),
    (("réseaux sociaux", "tiktok", "instagram", "facebook", "youtube", "meta ", "influenceur", "influenceuse", "plateforme", "algorithme", "modération", "contenu viral"),
     "L'actualité touche aux canaux par lesquels les publics découvrent et commentent les messages. Elle invite à revoir le choix des plateformes, les règles de modération et les indicateurs d'engagement, sans confondre visibilité algorithmique et adhésion réelle."),
    (("publicité", "campagne publicitaire", "marketing d'influence", "publicitaire", "annonceur", "marque lance", "nouvelle campagne", "spot publicitaire"),
     "Ce sujet interroge l'efficacité et l'acceptabilité des prises de parole de marque. Un communicant peut en tirer des enseignements sur le ciblage, la création, la cohérence entre promesse et preuves, ainsi que sur le risque de réaction négative du public."),
    (("intelligence artificielle", " ia ", "chatgpt", "openai", "anthropic", "modèle d'ia", "modèle de langage", "ia générative", "agent ia"),
     "Cette actualité liée à l'IA pose une question très concrète aux communicants : comment gagner en rapidité sans sacrifier l'exactitude, la transparence ni le ton de marque ? Elle invite à définir ce qui peut être automatisé et ce qui doit rester validé par un humain."),
    (("cyberattaque", "piratage", "rançongiciel", "ransomware", "fuite de données", "données personnelles volées", "cybersécurité"),
     "Au-delà de l'incident technique, une cyberattaque devient un test de confiance. La communication doit expliquer ce qui est établi, ce qui est encore vérifié, qui est concerné et quelles mesures sont prises, avec des mises à jour régulières plutôt que des assurances prématurées."),
    (("élection", "élections", "présidentielle", "législatives", "municipales", "scrutin", "vote", "candidat", "candidats", "sondage", "urnes"),
     "Le résultat et la campagne se lisent aussi à travers les récits, les symboles et les publics mobilisés. Pour les communicants, c'est un cas d'école de segmentation des audiences, de cadrage des messages et de vérification des chiffres ou sondages avant toute reprise."),
    (("budget", "loi de finances", "déficit public", "dépenses publiques", "impôt", "taxe", "fiscalité", "finances publiques"),
     "Un arbitrage budgétaire transforme des chiffres abstraits en choix qui touchent des publics précis. Les communicants institutionnels doivent rendre les conséquences compréhensibles, expliciter les compromis et anticiper les questions des bénéficiaires, contribuables ou partenaires."),
    (("manifestation", "manifestants", "mobilisation", "grève", "mouvement social", "syndicat", "syndicats", "blocage", "protestation"),
     "Cette mobilisation révèle un écart possible entre le discours des organisations et l'expérience vécue par leurs publics. Elle demande d'écouter les revendications, de reconnaître les impacts concrets et d'éviter les formules toutes faites qui risquent d'envenimer le dialogue."),
    (("loi", "projet de loi", "proposition de loi", "conseil constitutionnel", "règlement européen", "décret", "interdiction", "réglementation", "directive"),
     "L'évolution juridique peut modifier les pratiques des entreprises, des médias ou des institutions. Les communicants doivent traduire les règles en consignes compréhensibles, distinguer ce qui est déjà applicable de ce qui reste proposé, et éviter les annonces prématurées."),
    (("guerre", "frappes", "offensive", "armée", "militaire", "ot an", "otan", "missile", "cessez-le-feu", "conflit armé", "bombardement"),
     "Dans un contexte de conflit, les images et les récits circulent vite et peuvent être instrumentalisés. Les communicants doivent vérifier l'origine des contenus, dater les informations, contextualiser les chiffres et éviter de relayer des images choquantes ou non authentifiées."),
    (("diplomatie", "sommet", "ambassadeur", "ministre des affaires étrangères", "négociation", "accord international", "sanctions", "états-unis", "chine", "brésil", "iran", "ukraine", "gaza"),
     "Cet événement international peut déplacer les alliances, les sensibilités et les perceptions d'un pays ou d'une organisation. En communication, il faut adapter les références au contexte local, surveiller les réactions des différentes parties et ne pas plaquer une lecture nationale unique."),
    (("inflation", "pouvoir d'achat", "prix en hausse", "hausse des prix", "coût de la vie", "consommation", "panier moyen", "prix alimentaires"),
     "La hausse des prix touche directement les arbitrages quotidiens et la perception de la valeur. Les marques doivent examiner la sensibilité au prix, justifier leurs promesses par des bénéfices tangibles et éviter les messages déconnectés des contraintes vécues."),
    (("carburant", "pétrole", "gaz", "électricité", "prix de l'énergie", "énergie", "détroit d'ormuz"),
     "Les tensions énergétiques peuvent peser sur les coûts, les déplacements et les décisions de consommation. Pour les communicants, l'enjeu est d'expliquer les conséquences concrètes, de sourcer les données et de ne pas attribuer à une seule cause une évolution multifactorielle."),
    (("licenciement", "licenciements", "plan social", "suppression de postes", "emploi", "chômage", "recrutement", "salariés", "conditions de travail"),
     "Cette actualité concerne des personnes et la relation entre une organisation et ses équipes. La communication interne doit être cohérente avec les décisions réelles, préciser le calendrier et les accompagnements prévus, et respecter la dignité des personnes concernées."),
    (("entreprise", "entreprises", "résultat trimestriel", "chiffre d'affaires", "fusion", "rachat", "investissement", "faillite", "start-up", "startup"),
     "L'évolution de cette entreprise peut modifier son positionnement, ses attentes d'investisseurs ou la confiance de ses clients et salariés. Les communicants doivent relier les chiffres à une stratégie lisible, sans transformer une annonce ponctuelle en promesse excessive."),
    (("santé", "hôpital", "vaccin", "vaccination", "épidémie", "médecin", "patients", "médicament", "maladie", "soins", "santé publique"),
     "Sur un sujet de santé, la clarté et la prudence sont essentielles : un message imprécis peut créer de l'inquiétude ou de fausses attentes. Les communicants doivent s'appuyer sur des sources médicales fiables, expliquer les incertitudes et adapter le niveau de détail au public."),
    (("école", "lycée", "lycéens", "université", "étudiants", "enseignement", "éducation", "formation", "enseignants", "établissement scolaire"),
     "Cette actualité met en jeu les attentes des jeunes, des familles et des équipes éducatives. Elle éclaire la communication des établissements : expliquer les décisions, s'adresser aux publics concernés avec le bon ton et ne pas réduire une expérience diverse à un seul récit."),
    (("justice", "tribunal", "procès", "condamné", "condamnation", "enquête", "police", "interpellation", "accusation", "magistrat"),
     "Un dossier judiciaire exige une grande rigueur de formulation : présomption d'innocence, faits établis et déclarations doivent être distingués. Pour une organisation, une prise de parole mal calibrée peut créer un risque juridique et amplifier l'atteinte à la réputation."),
    (("climat", "réchauffement", "inondation", "sécheresse", "canicule", "incendie", "tempête", "biodiversité", "pollution", "émissions"),
     "L'événement rend un enjeu environnemental concret pour les territoires et les publics. Les communicants doivent privilégier des données attribuées, expliquer l'impact local et relier les engagements écologiques à des actions mesurables afin d'éviter le greenwashing."),
    (("transition énergétique", "énergies renouvelables", "éolien", "solaire", "nucléaire", "voiture électrique", "batterie", "décarbonation"),
     "Cette évolution autour de l'énergie confronte innovation, coût, usages et impact écologique. Elle fournit un cas utile pour communiquer sur une transition sans simplifier les arbitrages, en présentant les bénéfices, les limites et les preuves disponibles."),
    (("cinéma", "film", "série", "acteur", "actrice", "réalisateur", "festival", "streaming", "plateforme de streaming"),
     "Cette actualité culturelle montre comment une œuvre se construit une place dans l'attention collective. Les communicants peuvent observer le rôle de la bande-annonce, du bouche-à-oreille, des communautés de fans et du calendrier de sortie dans la visibilité d'un lancement."),
    (("livre", "roman", "écrivain", "écrivaine", "littérature", "goncourt", "prix littéraire", "édition", "librairie"),
     "Un sujet littéraire est aussi une histoire de prescription et de conversation culturelle. Il permet d'étudier comment critiques, prix, libraires et communautés contribuent à la visibilité d'une œuvre, sans réduire sa valeur au seul nombre de ventes."),
    (("musique", "chanteur", "chanteuse", "album", "concert", "tournée", "festival de musique"),
     "Cette actualité musicale illustre la construction d'une communauté autour d'un artiste ou d'un événement. Les équipes de communication peuvent observer l'articulation entre identité visuelle, réseaux sociaux, expérience en direct et relais des fans."),
    (("sport", "football", "rugby", "tennis", "basket", "formule 1", "grand prix", "championnat", "olympique", "coupe du monde", "match", "athlète"),
     "Le sport associe performance, émotion collective et exposition médiatique. Cette actualité permet d'analyser la réputation d'un athlète ou d'un club, la communication des sponsors et la nécessité de réagir vite sans commenter à chaud des informations non vérifiées."),
    (("découverte scientifique", "chercheurs", "chercheur", "recherche", "étude scientifique", "publication scientifique", "nobel", "astronomie", "espace", "nasa", "neurone", "mathématiques"),
     "La difficulté ici est de rendre un résultat complexe accessible sans le sur-vendre. Un communicant doit distinguer une piste de recherche d'une application confirmée, expliquer ce qui a réellement été démontré et citer l'équipe ou la publication à l'origine du résultat."),
    (("média", "médias", "journaliste", "journalisme", "télévision", "radio", "presse", "chaîne d'information", "rédaction", "désinformation", "fake news"),
     "Cette actualité touche à la fabrication et à la circulation de l'information. Les communicants doivent connaître le rôle des rédactions, vérifier l'origine des chiffres et images, et distinguer relation presse, communication institutionnelle et travail journalistique indépendant."),
]

CATEGORY_ANGLE_FALLBACKS = {
    "Politique": "Cette décision ou prise de position influe sur le débat public. Le communicant doit identifier les publics touchés, séparer annonce et mesure effective et anticiper les questions qui pourraient émerger.",
    "Économie": "Cette évolution peut modifier les comportements d'achat ou les décisions des organisations. Elle invite à réévaluer les messages sur le prix, la valeur et les conséquences concrètes pour les publics concernés.",
    "Société": "Cette actualité révèle une attente ou une tension vécue par une partie de la population. Elle invite à écouter les personnes concernées, éviter les généralisations et choisir des formulations empathiques et précises.",
    "International": "Le contexte international change la manière dont un événement est interprété selon les pays et les publics. Les communicants doivent vérifier les faits, donner les repères utiles et tenir compte des sensibilités locales.",
    "Sciences & tech": "Cette actualité demande de rendre un sujet technique compréhensible sans promettre davantage que ce que les faits établissent. Le communicant doit expliquer les usages, les limites et les questions éthiques.",
    "Culture": "Cette actualité participe aux références et conversations culturelles du moment. Elle peut inspirer une campagne, à condition de comprendre le contexte de l'œuvre et de ne pas instrumentaliser les communautés qu'elle mobilise.",
    "Sport": "Cette actualité génère des émotions et rassemble des communautés engagées. Elle invite à observer le récit médiatique, les partenaires associés et les effets possibles sur l'image des personnes ou organisations concernées.",
    "Médias & communication": "Cette actualité touche à la diffusion des messages et à la confiance dans les canaux. Elle invite à penser transparence, responsabilité éditoriale et adéquation entre canal, message et public.",
    "Environnement": "Cette actualité rend visibles des enjeux environnementaux et des attentes envers les organisations. Toute communication associée doit s'appuyer sur des éléments vérifiables et relier les promesses à des actions concrètes.",
}

def communication_angle_for(title: str, summary: str, category: str) -> str:
    """Produit un angle adapté aux indices présents dans le titre et le résumé RSS."""
    headline = clean_text(title).strip(" .:;—–")
    # Les mêmes règles par mots entiers évitent les faux positifs tels que
    # « loi » repérée au milieu du mot « emplois ».
    content = f" {normalize_keyword_text(f'{headline} {clean_text(summary)}')} "
    for keywords, angle in ARTICLE_ANGLE_RULES:
        if any(f" {normalize_keyword_text(keyword)} " in content for keyword in keywords):
            return f"{angle} Sujet suivi : « {headline[:150]} » .".replace(" » .", " ».")
    fallback = CATEGORY_ANGLE_FALLBACKS.get(category, "Cette actualité peut faire évoluer les attentes des publics et les conversations autour des organisations.")
    return f"{fallback} Pour travailler ce cas, partez du sujet précis — « {headline[:150]} » — puis identifiez les publics concernés, le message à adapter et les preuves nécessaires avant de communiquer."

def clean_text(value: str) -> str:
    value = html.unescape(re.sub(r"<[^>]+>", " ", value or ""))
    return re.sub(r"\s+", " ", value).strip()

def parse_date(entry):
    for key in ("published", "updated", "created"):
        value = entry.get(key)
        if value:
            try:
                dt = parsedate_to_datetime(value)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc).isoformat()
            except Exception:
                pass
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            try:
                return datetime.fromtimestamp(time.mktime(value), timezone.utc).isoformat()
            except Exception:
                pass
    return None

def categorize(text: str) -> str:
    normalized = f" {normalize_keyword_text(text)} "
    for category, keywords in NORMALIZED_CATEGORY_RULES:
        if any(f" {keyword} " in normalized for keyword in keywords):
            return category
    return "Société"

def short_summary(entry) -> str:
    """Retient l'extrait RSS le plus riche sans récupérer ni reproduire l'article complet."""
    candidates = []
    for key in ("summary", "description"):
        value = clean_text(entry.get(key, ""))
        if value:
            candidates.append(value)
    content_values = entry.get("content", []) or []
    if isinstance(content_values, dict):
        content_values = [content_values]
    for item in content_values:
        if isinstance(item, dict):
            value = clean_text(item.get("value", ""))
            if value:
                candidates.append(value)
    text = max(candidates, key=len) if candidates else ""
    if len(text) > 360:
        text = text[:357].rsplit(" ", 1)[0] + "…"
    return text or "Consultez l’article original pour retrouver le contexte, les détails et les éventuelles mises à jour."

# Mots fonctionnels et termes trop génériques pour rapprocher deux actualités.
STORY_STOPWORDS = set("""
a au aux avec ce ces dans de des du elle elles en et eux il ils je la le les leur leurs lui ma mais me meme memes mes moi mon ne nos notre nous on ou par pas pour qu que quelle quelles quel quels qui sa sans se ses si son sont sous sur ta te tes toi ton toutes tout tres tu un une vos votre vous cela cette cet donc apres avant aussi alors ainsi autour autre autres avoir etre fait font faire fois selon entre depuis pendant durant chez via vers ici encore quand comme plus moins peu peut peuvent doit doivent apres annonce annoncent annoncee annoncees question questions sujet sujets actualite actualites information informations derniere dernier aujourd hui lundi mardi mercredi jeudi vendredi samedi dimanche france francais francaise francaises francais monde national nationale nationales europe europeen europeenne grande grands grand nouvelles nouvelle nouveaux nouveau premier premiere premiers premieres plusieurs chaque tout toute toutes certains certaines notamment notamment deja serait seraient devrait pourraient etre ete faire faire leurs alors ainsi autant notamment contre autre autres alors bref video videos direct directes suivi suivent revenir revient voir voici voila apres suite cours jour jours semaine semaines lundi mardi mercredi jeudi vendredi samedi dimanche matin soir nuit heures heure parmi partie parties ville villes pays presse media medias source sources article articles selon apres depeche depêche ce lundi ce mardi francais francaise francaises franceinfo monde monde entier
""".split())
SOURCE_PRIORITY = {
    "Franceinfo (TV)": 9, "France Info (Radio)": 9, "Le Monde": 9, "Le Figaro": 8,
    "Mediapart": 8, "TF1 Info (TF1 / LCI)": 8, "France 24": 8, "RFI": 8,
    "BFMTV": 7, "CNews": 7, "L'Opinion": 7, "Libération": 7,
    "Les Échos": 7, "Le Point": 7, "L'Express": 7, "L'Obs": 7,
    "Sud Ouest": 7, "La Voix du Nord": 7, "Ouest-France": 7,
    "Courrier International": 7, "Euronews": 7, "France Inter": 7,
    "France Culture": 7, "RMC": 7, "L'Humanité": 6, "La Croix": 6,
    "20 Minutes": 6, "Le Dauphiné Libéré": 6, "La Dépêche du Midi": 6,
    "Midi Libre": 6, "Le JDD": 6, "Alternatives économiques": 6,
    "Paris Match": 6, "Valeurs actuelles": 6, "Public Sénat": 6,
    "LCP": 6, "Konbini": 5, "Actu.fr": 5, "Next.ink": 5,
    "Le Monde Informatique": 5, "Futura": 5, "Reporterre": 5,
    "Télérama": 5, "CB News": 4, "Creapills": 4,
    "INA – La Revue des médias": 4,
}

def story_tokens(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKD", clean_text(text)).encode("ascii", "ignore").decode("ascii").lower()
    tokens = set(re.findall(r"[a-z0-9]{3,}", normalized))
    result = set()
    for token in tokens:
        if token in STORY_STOPWORDS or token.isdigit():
            continue
        # Normalisation légère du pluriel français pour faire correspondre, par ex.,
        # « manifestations » et « manifestation », sans dépendance à un outil externe.
        stem = token[:-1] if len(token) > 4 and token.endswith("s") else token
        if stem not in STORY_STOPWORDS and len(stem) >= 3:
            result.add(stem)
    return result

def parse_iso_datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None

def build_featured_stories(articles: list[dict], now: datetime):
    """Classe 20 sujets de la fenêtre glissante de 30 jours selon la couverture croisée.

    Les articles proches sont regroupés à partir du chevauchement pondéré des termes
    de leurs titres et résumés. Le score combine diversité des médias, volume d'articles
    associés et fraîcheur. C'est un indicateur transparent de couverture, pas un modèle
    éditorial capable de juger le fond ou de vérifier les faits.
    """
    window_start = now - timedelta(days=FEATURED_DAYS)
    recent = []
    for article in articles:
        published = parse_iso_datetime(article.get("published_at"))
        if published and window_start <= published <= now + timedelta(minutes=10):
            item = dict(article)
            item["_published_dt"] = published
            item["_title_terms"] = story_tokens(item.get("title", ""))
            item["_all_terms"] = story_tokens((item.get("title", "") + " " + (item.get("summary", "") or "")[:500]))
            recent.append(item)
    if not recent:
        return [], window_start, len(recent), 0

    # IDF réduit le poids des mots omniprésents dans le corpus du mois.
    doc_frequency = {}
    for item in recent:
        for term in item["_all_terms"]:
            doc_frequency[term] = doc_frequency.get(term, 0) + 1
    n_docs = len(recent)
    idf = {term: math.log(1 + (n_docs + 1) / (freq + 1)) for term, freq in doc_frequency.items()}

    def term_weight(terms):
        return sum(idf.get(term, 1.0) for term in terms)

    def related(a, b):
        shared_title = a["_title_terms"] & b["_title_terms"]
        title_min = min(term_weight(a["_title_terms"]), term_weight(b["_title_terms"]))
        title_overlap = (term_weight(shared_title) / title_min) if title_min else 0.0
        if len(shared_title) >= 2 and title_overlap >= 0.30:
            return True
        shared_all = a["_all_terms"] & b["_all_terms"]
        if len(shared_all) < 3:
            return False
        min_weight = min(term_weight(a["_all_terms"]), term_weight(b["_all_terms"]))
        if not min_weight:
            return False
        containment = term_weight(shared_all) / min_weight
        union = a["_all_terms"] | b["_all_terms"]
        jaccard = term_weight(shared_all) / max(term_weight(union), 1e-9)
        return containment >= 0.34 and jaccard >= 0.10

    # Union-find : chaque composante devient un sujet, potentiellement cité par plusieurs médias.
    parents = list(range(n_docs))
    def find(x):
        while parents[x] != x:
            parents[x] = parents[parents[x]]
            x = parents[x]
        return x
    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parents[ry] = rx

    for i in range(n_docs):
        for j in range(i + 1, n_docs):
            if related(recent[i], recent[j]):
                union(i, j)

    clusters = {}
    for index, article in enumerate(recent):
        clusters.setdefault(find(index), []).append(article)

    stories = []
    for group in clusters.values():
        unique_sources = sorted(
            {safe for safe in (x.get("source", "") for x in group) if safe},
            key=lambda name: (-SOURCE_PRIORITY.get(name, 0), name.lower())
        )
        newest = max(x["_published_dt"] for x in group)
        age_hours = max(0.0, (now - newest).total_seconds() / 3600)
        freshness = max(0.0, 1.0 - age_hours / (FEATURED_DAYS * 24))
        # La diversité des médias pèse davantage qu'une répétition par une seule source.
        feed_positions = [max(0.0, 1.0 - ((min(int(x.get("feed_rank", MAX_PER_SOURCE)), MAX_PER_SOURCE) - 1) / max(1, MAX_PER_SOURCE - 1))) for x in group]
        feed_prominence = sum(feed_positions) / len(feed_positions) if feed_positions else 0.0
        score = (4.5 * math.log2(len(unique_sources) + 1)
                 + 1.35 * math.log2(len(group) + 1)
                 + 2.0 * freshness
                 + 1.1 * feed_prominence)
        # Favoriser un titre récent, avec un extrait lisible et provenant d'une source suivie.
        representative = max(group, key=lambda x: (
            x["_published_dt"].timestamp() / 86400
            + min(len(x.get("summary", "")), 260) / 260 * 0.15
            + SOURCE_PRIORITY.get(x.get("source", ""), 0) / 100
        ))
        story = {k: v for k, v in representative.items() if not k.startswith("_")}
        story.update({
            "coverage_sources": unique_sources,
            "coverage_count": len(unique_sources),
            "mention_count": len(group),
            "importance_score": round(score, 3),
            "latest_coverage_at": newest.isoformat(),
        })
        stories.append(story)

    stories.sort(key=lambda x: (x["importance_score"], x.get("published_at") or ""), reverse=True)
    distinct_sources = len({x.get("source") for x in recent if x.get("source")})
    return stories[:FEATURED_LIMIT], window_start, len(recent), distinct_sources

def fetch_feed_articles(feed: dict):
    """Récupère un flux indépendamment ; une source en panne n'arrête pas les autres."""
    try:
        response = requests.get(
            feed["url"],
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
        if not parsed.entries:
            return feed["name"], [], "flux vide ou format non reconnu"

        collected = []
        for feed_rank, entry in enumerate(parsed.entries, start=1):
            if feed_rank > MAX_PER_SOURCE:
                break
            title = clean_text(entry.get("title", ""))
            url = entry.get("link", "")
            if not title or not url.startswith(("http://", "https://")):
                continue
            normalized_url = url.split("#", 1)[0].split("?", 1)[0].rstrip("/")
            fingerprint = hashlib.sha256(
                (title.lower() + "|" + normalized_url).encode()
            ).hexdigest()
            published = parse_date(entry)
            raw_summary = clean_text(entry.get("summary", ""))
            summary = short_summary(entry)
            category = categorize(title + " " + raw_summary)
            collected.append({
                "id": fingerprint[:12],
                "title": title[:240],
                "summary": summary,
                "source": feed["name"],
                "feed_rank": feed_rank,
                "url": url,
                "published_at": published,
                "category": category,
                "communication_angle": communication_angle_for(title, summary, category),
            })
        if not collected:
            return feed["name"], [], "aucun article avec titre et lien exploitable"
        return feed["name"], collected, None
    except Exception as exc:
        return feed["name"], [], f"{type(exc).__name__}: {exc}"


def deduplicate_articles(articles: list[dict], max_age_hours: int = 72) -> list[dict]:
    """Regroupe les articles qui relatent très probablement le même événement.

    La détection est volontairement stricte pour ne pas fusionner deux actualités
    simplement parce qu'elles concernent la même personnalité ou le même thème.
    L'article avec l'extrait RSS le plus informatif devient la version affichée.
    """
    items = [dict(article) for article in articles if isinstance(article, dict)]
    count = len(items)
    if count < 2:
        return items

    parents = list(range(count))

    def find(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(a, b):
        root_a, root_b = find(a), find(b)
        if root_a != root_b:
            parents[root_b] = root_a

    def canonical_url(value):
        return str(value or "").split("#", 1)[0].split("?", 1)[0].rstrip("/").lower()

    def are_same_story(a, b):
        date_a = parse_iso_datetime(a.get("published_at"))
        date_b = parse_iso_datetime(b.get("published_at"))
        if date_a and date_b and abs((date_a - date_b).total_seconds()) > max_age_hours * 3600:
            return False

        title_a = story_tokens(a.get("title", ""))
        title_b = story_tokens(b.get("title", ""))
        shared_title = title_a & title_b
        title_union = title_a | title_b
        title_containment = len(shared_title) / max(1, min(len(title_a), len(title_b)))
        title_jaccard = len(shared_title) / max(1, len(title_union))
        if len(shared_title) >= 2 and title_containment >= 0.72 and title_jaccard >= 0.34:
            return True

        all_a = story_tokens((a.get("title", "") + " " + a.get("summary", ""))[:900])
        all_b = story_tokens((b.get("title", "") + " " + b.get("summary", ""))[:900])
        shared_all = all_a & all_b
        if len(shared_all) < 5 or not shared_title:
            return False
        containment = len(shared_all) / max(1, min(len(all_a), len(all_b)))
        jaccard = len(shared_all) / max(1, len(all_a | all_b))
        return containment >= 0.66 and jaccard >= 0.18

    # Les URL strictement identiques sont rapprochées sans tenir compte des paramètres
    # de suivi. Les autres comparaisons restent limitées à une fenêtre de 72 heures.
    url_owner = {}
    dated_indices = []
    for index, item in enumerate(items):
        url = canonical_url(item.get("url"))
        if url:
            if url in url_owner:
                union(index, url_owner[url])
            else:
                url_owner[url] = index
        published = parse_iso_datetime(item.get("published_at"))
        dated_indices.append((published, index))

    dated_indices.sort(key=lambda pair: pair[0] or datetime.min.replace(tzinfo=timezone.utc))
    for position, (date_a, index_a) in enumerate(dated_indices):
        for date_b, index_b in dated_indices[position + 1:]:
            if date_a and date_b and (date_b - date_a).total_seconds() > max_age_hours * 3600:
                break
            if index_a == index_b:
                continue
            if are_same_story(items[index_a], items[index_b]):
                union(index_a, index_b)

    groups = {}
    for index, item in enumerate(items):
        groups.setdefault(find(index), []).append(item)

    deduplicated = []
    for group in groups.values():
        sources = set()
        for item in group:
            source = str(item.get("source") or "").strip()
            if source:
                sources.add(source)
            for previous_source in item.get("coverage_sources", []) or []:
                if isinstance(previous_source, str) and previous_source.strip():
                    sources.add(previous_source.strip())

        dated_group = [
            parsed for parsed in (parse_iso_datetime(item.get("published_at")) for item in group)
            if parsed is not None
        ]
        newest_in_group = max(dated_group) if dated_group else None

        def completeness(item):
            summary = str(item.get("summary") or "")
            title = str(item.get("title") or "")
            informative_terms = len(story_tokens(summary))
            source_score = SOURCE_PRIORITY.get(item.get("source", ""), 0)
            published = parse_iso_datetime(item.get("published_at"))
            age_hours = (
                max(0.0, (newest_in_group - published).total_seconds() / 3600)
                if newest_in_group and published else max_age_hours
            )
            freshness_score = max(0.0, 6.0 - min(age_hours, max_age_hours) / max_age_hours * 6.0)
            return (
                min(len(summary), 360)
                + min(informative_terms, 55) * 1.5
                + min(len(title), 180) * 0.12
                + source_score * 1.5
                + freshness_score
            )

        representative = dict(max(group, key=completeness))
        ordered_sources = sorted(
            sources,
            key=lambda name: (-SOURCE_PRIORITY.get(name, 0), name.casefold())
        )
        representative.update({
            "coverage_sources": ordered_sources,
            "coverage_count": len(ordered_sources),
            "mention_count": len(group),
        })
        deduplicated.append(representative)

    deduplicated.sort(
        key=lambda item: item.get("published_at") or "",
        reverse=True,
    )
    return deduplicated


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    articles, errors = [], []
    # Les flux sont récupérés en parallèle pour que l'ajout de sources ne dépasse
    # pas le délai maximal du workflow lorsque certains éditeurs répondent lentement.
    with ThreadPoolExecutor(max_workers=8) as executor:
        for source_name, feed_articles, error in executor.map(fetch_feed_articles, FEEDS):
            articles.extend(feed_articles)
            if error:
                print(f"[WARN] Flux indisponible {source_name}: {error}")
                errors.append(source_name)

    now_dt = datetime.now(timezone.utc)
    previous_data = {}
    if OUT.exists():
        try:
            previous_data = json.loads(OUT.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[WARN] Ancien fichier de veille illisible : {type(exc).__name__}: {exc}")

    # Si tous les flux échouent, conserver le dernier fichier valide sans le remplacer par un corpus vide.
    if not articles and OUT.exists():
        if not previous_data:
            print("Aucun flux récupéré et anciennes données illisibles : fichier existant laissé intact.")
            return
        previous_data["note"] = "La collecte a échoué pour tous les flux. Les articles affichés proviennent de la dernière collecte réussie."
        previous_data["last_attempt"] = now_dt.isoformat()
        OUT.write_text(json.dumps(previous_data, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Aucun flux récupéré : les données précédentes sont conservées.")
        return

    # En cas de panne partielle, conserver pendant 30 jours les articles des médias en erreur.
    # Cela évite qu'une indisponibilité ponctuelle fasse disparaître tout un média du site.
    if errors and previous_data:
        failed_sources = set(errors)
        cutoff = now_dt - timedelta(days=30)
        known_ids = {str(item.get("id")) for item in articles if item.get("id")}
        known_urls = {
            str(item.get("url", "")).split("?", 1)[0].split("#", 1)[0].rstrip("/")
            for item in articles if item.get("url")
        }
        previous_articles = previous_data.get("articles", [])
        if isinstance(previous_articles, list):
            for old_article in previous_articles:
                if not isinstance(old_article, dict) or old_article.get("source") not in failed_sources:
                    continue
                published = parse_iso_datetime(old_article.get("published_at"))
                if not published or not cutoff <= published <= now_dt + timedelta(minutes=10):
                    continue
                old_id = str(old_article.get("id") or "")
                old_url = str(old_article.get("url") or "").split("?", 1)[0].split("#", 1)[0].rstrip("/")
                if (old_id and old_id in known_ids) or (old_url and old_url in known_urls):
                    continue
                articles.append(dict(old_article))
                if old_id:
                    known_ids.add(old_id)
                if old_url:
                    known_urls.add(old_url)

    articles.sort(key=lambda item: item.get("published_at") or "", reverse=True)
    all_fetched_articles = list(articles)
    unique_articles = deduplicate_articles(all_fetched_articles)
    articles = unique_articles[:MAX_TOTAL]
    now = now_dt.isoformat()
    # Le baromètre continue d'examiner les articles de tous les médias, avant dédoublonnage,
    # afin de mesurer correctement la couverture d'un même sujet par plusieurs rédactions.
    featured_news, window_start, featured_pool_count, featured_sources_count = build_featured_stories(all_fetched_articles, now_dt)
    data = {
        "last_updated": now,
        "last_attempt": now,
        "timezone": "UTC; affichage en heure de Paris dans le navigateur",
        "article_count": len(articles),
        "raw_article_count": len(all_fetched_articles),
        "unique_story_count": len(unique_articles),
        "sources_configured": len(FEEDS),
        "sources_with_errors": errors,
        "note": ("Certains flux n’ont pas répondu lors de cette collecte : " + ", ".join(errors) + ". La sélection peut donc être incomplète.") if errors else "",
        "featured_window_start": window_start.isoformat(),
        "featured_window_end": now,
        "featured_pool_count": featured_pool_count,
        "featured_sources_count": featured_sources_count,
        "featured_ranking_method": "diversité des médias, volume d'articles liés, position dans les flux RSS et fraîcheur sur 30 jours",
        "featured_news": featured_news,
        "articles": articles,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Collecte terminée : {len(articles)} articles, {len(featured_news)} sujets mis en avant sur 30 jours, {len(errors)} flux en erreur.")

if __name__ == "__main__":
    main()
