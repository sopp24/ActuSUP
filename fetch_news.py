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
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import requests

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "news.json"
MAX_PER_SOURCE = 25
MAX_TOTAL = 160
FEATURED_LIMIT = 20
FEATURED_DAYS = 7
TIMEOUT = 20
USER_AGENT = "ActuSUP-NewsReader/1.0 (+https://github.com/; educational project)"

# Les URL de flux peuvent évoluer ; une source en erreur n'empêche pas les autres de fonctionner.
FEEDS = [
    # Médias généralistes et information continue
    {"name": "franceinfo", "url": "https://www.francetvinfo.fr/titres.rss"},
    {"name": "France 24", "url": "https://www.france24.com/fr/rss"},
    {"name": "RFI", "url": "https://www.rfi.fr/fr/rss"},
    {"name": "Le Monde", "url": "https://www.lemonde.fr/rss/une.xml"},
    {"name": "Le Figaro", "url": "https://www.lefigaro.fr/rss/figaro_actualites.xml"},
    {"name": "BFMTV", "url": "https://www.bfmtv.com/rss/news-24-7/"},
    {"name": "20 Minutes", "url": "https://www.20minutes.fr/feeds/rss-une.xml"},
    {"name": "Actu.fr", "url": "https://actu.fr/rss.xml"},
    {"name": "Courrier International", "url": "https://www.courrierinternational.com/feed/all/rss.xml"},
    {"name": "Euronews", "url": "https://fr.euronews.com/rss"},
    {"name": "La Croix – International", "url": "https://www.la-croix.com/feeds/rss/international.xml"},
    {"name": "Libération", "url": "https://www.liberation.fr/arc/outboundfeeds/rss-all/?outputType=xml"},
    {"name": "Les Échos", "url": "https://www.lesechos.fr/rss/rss_une.xml"},
    {"name": "Ouest-France", "url": "https://www.ouest-france.fr/rss-en-continu.xml"},
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
    ("Économie", ["économie", "économique", "inflation", "emploi", "chômage", "entreprise", "entreprises", "bourse", "banque", "budget", "croissance", "prix", "carburant", "pouvoir d'achat", "consommation", "commerce", "industrie", "impôt", "taxe", "euro"]),
    ("Société", ["société", "éducation", "école", "étudiant", "étudiants", "santé", "hôpital", "justice", "police", "violence", "logement", "famille", "retraite", "manifestation", "social", "inégalité", "immigration"]),
    ("Sciences & tech", ["science", "scientifique", "recherche", "intelligence artificielle", " ia ", "technologie", "numérique", "cyber", "cybersécurité", "espace", "nasa", "robot", "découverte", "médecine", "vaccin", "santé numérique"]),
    ("Culture", ["culture", "cinéma", "film", "série", "musique", "livre", "roman", "littérature", "exposition", "musée", "théâtre", "artiste", "festival", "goncourt", "prix littéraire", "jeu vidéo"]),
    ("Sport", ["sport", "football", "rugby", "tennis", "basket", "olympique", "olympisme", "formule 1", "f1", "tour de france", "ligue 1", "championnat", "match", "athlète"]),
    ("Environnement", ["climat", "environnement", "écologie", "écologique", "biodiversité", "pollution", "réchauffement", "énergie", "énergies", "sécheresse", "inondation", "forêt", "incendie", "transition énergétique"]),
    ("International", ["international", "monde", "ukraine", "russie", "états-unis", "états unis", "chine", "iran", "israël", "gaza", "palestine", "onu", "otan", "afrique", "europe", "union européenne", "guerre", "diplomatie", "brésil"]),
]

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
    content = f" {headline} {clean_text(summary)} ".lower()
    for keywords, angle in ARTICLE_ANGLE_RULES:
        if any(keyword in content for keyword in keywords):
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
    lower = f" {text.lower()} "
    for category, keywords in CATEGORY_RULES:
        if any(word in lower for word in keywords):
            return category
    return "Société"

def angle_for(category: str) -> str:
    return next((angle for cat, angle in ANGLE_RULES if cat == category), DEFAULT_ANGLE)

def short_summary(entry) -> str:
    for key in ("summary", "description"):
        text = clean_text(entry.get(key, ""))
        if text and len(text) > 35:
            if len(text) > 360:
                text = text[:357].rsplit(" ", 1)[0] + "…"
            return text
    return "Consultez l’article original pour retrouver le contexte, les détails et les éventuelles mises à jour."

# Mots fonctionnels et termes trop génériques pour rapprocher deux actualités.
STORY_STOPWORDS = set("""
a au aux avec ce ces dans de des du elle elles en et eux il ils je la le les leur leurs lui ma mais me meme memes mes moi mon ne nos notre nous on ou par pas pour qu que quelle quelles quel quels qui sa sans se ses si son sont sous sur ta te tes toi ton toutes tout tres tu un une vos votre vous cela cette cet donc apres avant aussi alors ainsi autour autre autres avoir etre fait font faire fois selon entre depuis pendant durant chez via vers ici encore quand comme plus moins peu peut peuvent doit doivent apres annonce annoncent annoncee annoncees question questions sujet sujets actualite actualites information informations derniere dernier aujourd hui lundi mardi mercredi jeudi vendredi samedi dimanche france francais francaise francaises francais monde national nationale nationales europe europeen europeenne grande grands grand nouvelles nouvelle nouveaux nouveau premier premiere premiers premieres plusieurs chaque tout toute toutes certains certaines notamment notamment deja serait seraient devrait pourraient etre ete faire faire leurs alors ainsi autant notamment contre autre autres alors bref video videos direct directes suivi suivent revenir revient voir voici voila apres suite cours jour jours semaine semaines lundi mardi mercredi jeudi vendredi samedi dimanche matin soir nuit heures heure parmi partie parties ville villes pays presse media medias source sources article articles selon apres depeche depêche ce lundi ce mardi francais francaise francaises franceinfo monde monde entier
""".split())
SOURCE_PRIORITY = {
    "franceinfo": 9, "Le Monde": 9, "Le Figaro": 8,
    "France 24": 8, "RFI": 8, "BFMTV": 7,
    "Courrier International": 7, "Euronews": 7, "Libération": 7,
    "Les Échos": 7, "20 Minutes": 6, "La Croix – International": 6,
    "Ouest-France": 6, "Public Sénat": 6, "LCP": 6,
    "Actu.fr": 5, "Next.ink": 5, "Le Monde Informatique": 5,
    "Futura": 5, "Reporterre": 5, "Télérama": 5,
    "CB News": 4, "Creapills": 4, "INA – La Revue des médias": 4,
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
    """Classe 20 sujets de la fenêtre glissante de 7 jours selon la couverture croisée.

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

    # IDF réduit le poids des mots omniprésents dans le corpus de la semaine.
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

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    articles, errors = [], []
    seen = set()
    for feed in FEEDS:
        try:
            response = session.get(feed["url"], timeout=TIMEOUT)
            response.raise_for_status()
            parsed = feedparser.parse(response.content)
            if not parsed.entries:
                errors.append(feed["name"])
                continue
            source_count = 0
            for feed_rank, entry in enumerate(parsed.entries, start=1):
                if feed_rank > MAX_PER_SOURCE:
                    break
                title = clean_text(entry.get("title", ""))
                url = entry.get("link", "")
                if not title or not url.startswith(("http://", "https://")):
                    continue
                fingerprint = hashlib.sha256((title.lower() + "|" + url.split("?")[0]).encode()).hexdigest()
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                published = parse_date(entry)
                category = categorize(title + " " + clean_text(entry.get("summary", "")))
                articles.append({
                    "id": fingerprint[:12],
                    "title": title[:240],
                    "summary": short_summary(entry),
                    "source": feed["name"],
                    "feed_rank": feed_rank,
                    "url": url,
                    "published_at": published,
                    "category": category,
                    "communication_angle": communication_angle_for(title, clean_text(entry.get("summary", "")), category),
                })
                source_count += 1
                if source_count >= MAX_PER_SOURCE:
                    break
        except Exception as exc:
            print(f"[WARN] Flux indisponible {feed['name']}: {type(exc).__name__}: {exc}")
            errors.append(feed["name"])

    articles.sort(key=lambda item: item.get("published_at") or "", reverse=True)
    all_fetched_articles = list(articles)
    articles = articles[:MAX_TOTAL]
    # Si tous les flux échouent, préserver les dernières données publiées plutôt que vider le site.
    if not articles and OUT.exists():
        old = json.loads(OUT.read_text(encoding="utf-8"))
        old["note"] = "La collecte a échoué pour tous les flux. Les articles affichés proviennent de la dernière collecte réussie."
        old["last_attempt"] = datetime.now(timezone.utc).isoformat()
        OUT.write_text(json.dumps(old, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Aucun flux récupéré : les données précédentes sont conservées.")
        return

    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    featured_news, window_start, featured_pool_count, featured_sources_count = build_featured_stories(all_fetched_articles, now_dt)
    data = {
        "last_updated": now,
        "last_attempt": now,
        "timezone": "UTC; affichage en heure de Paris dans le navigateur",
        "article_count": len(articles),
        "sources_configured": len(FEEDS),
        "sources_with_errors": errors,
        "note": ("Certains flux n’ont pas répondu lors de cette collecte : " + ", ".join(errors) + ". La sélection peut donc être incomplète.") if errors else "",
        "featured_window_start": window_start.isoformat(),
        "featured_window_end": now,
        "featured_pool_count": featured_pool_count,
        "featured_sources_count": featured_sources_count,
        "featured_ranking_method": "diversité des médias, volume d'articles liés, position dans les flux RSS et fraîcheur sur 7 jours",
        "featured_news": featured_news,
        "articles": articles,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Collecte terminée : {len(articles)} articles, {len(featured_news)} sujets mis en avant sur 7 jours, {len(errors)} flux en erreur.")

if __name__ == "__main__":
    main()
