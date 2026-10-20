#!/usr/bin/env python3
"""Collecte des flux RSS de médias francophones et génération de data/news.json."""
from __future__ import annotations
import hashlib
import json
import re
import time
import html
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

import feedparser
import requests

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "news.json"
MAX_PER_SOURCE = 25
MAX_TOTAL = 160
TIMEOUT = 20
USER_AGENT = "ActuSUP-NewsReader/1.0 (+https://github.com/; educational project)"

# Les URL de flux peuvent évoluer ; une source en erreur n'empêche pas les autres de fonctionner.
FEEDS = [
    {"name": "franceinfo", "url": "https://www.francetvinfo.fr/titres.rss"},
    {"name": "France 24", "url": "https://www.france24.com/fr/rss"},
    {"name": "RFI", "url": "https://www.rfi.fr/fr/rss"},
    {"name": "Le Monde", "url": "https://www.lemonde.fr/rss/une.xml"},
    {"name": "Libération", "url": "https://www.liberation.fr/arc/outboundfeeds/rss-all/?outputType=xml"},
    {"name": "Les Échos", "url": "https://www.lesechos.fr/rss/rss_une.xml"},
    {"name": "Ouest-France", "url": "https://www.ouest-france.fr/rss-en-continu.xml"},
    {"name": "Public Sénat", "url": "https://www.publicsenat.fr/rss"},
    {"name": "LCP", "url": "https://lcp.fr/rss.xml"},
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

ANGLE_RULES = [
    ("Médias & communication", "Le sujet touche directement aux médias, aux plateformes ou à la circulation des messages. Pour les communicants, il invite à réfléchir aux formats, à la confiance, à la modération et à la manière dont les publics reçoivent l’information."),
    ("Politique", "Une décision ou un débat politique peut modifier les priorités des institutions, des entreprises et des citoyens. Les communicants doivent en comprendre le contexte pour adapter leurs messages, anticiper les réactions et éviter les contresens."),
    ("Économie", "Les évolutions économiques influencent le pouvoir d’achat, les comportements de consommation et les décisions des organisations. Elles peuvent faire évoluer les arguments de marque, les attentes des publics et les sujets sensibles à traiter."),
    ("Société", "Ce sujet révèle des préoccupations, des valeurs ou des tensions sociales. Il aide les communicants à mieux comprendre leurs publics, choisir des mots justes et concevoir des messages inclusifs et contextualisés."),
    ("Sciences & tech", "Les innovations scientifiques et technologiques font émerger de nouveaux usages, des opportunités et des questions éthiques. Les communicants doivent rendre ces enjeux compréhensibles sans exagérer les résultats ni confondre hypothèse et fait établi."),
    ("Culture", "Les œuvres, les artistes et les références culturelles nourrissent les imaginaires collectifs. Les connaître aide à trouver des références pertinentes, comprendre les tendances et créer des campagnes qui résonnent avec leurs publics."),
    ("Sport", "Le sport concentre des communautés engagées, des récits puissants et des enjeux de sponsoring, d’image et de réputation. Il fournit des exemples concrets de communication événementielle, de gestion de crise et de mobilisation des fans."),
    ("Environnement", "Les enjeux environnementaux pèsent sur les attentes du public et les engagements des organisations. Les communicants doivent étayer les affirmations, éviter le greenwashing et relier les promesses aux actions vérifiables."),
    ("International", "Un événement international peut avoir des conséquences politiques, économiques et culturelles bien au-delà de ses frontières. Il permet aux communicants d’anticiper les sensibilités locales, les risques réputationnels et les différences de contexte."),
]
DEFAULT_ANGLE = "Cette actualité peut faire évoluer les conversations publiques et les attentes des publics. Pour un communicant, elle constitue un contexte à comprendre avant de prendre la parole, de choisir un angle éditorial ou de conseiller une organisation."

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
            for entry in parsed.entries:
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
                    "url": url,
                    "published_at": published,
                    "category": category,
                    "communication_angle": angle_for(category),
                })
                source_count += 1
                if source_count >= MAX_PER_SOURCE:
                    break
        except Exception as exc:
            print(f"[WARN] Flux indisponible {feed['name']}: {type(exc).__name__}: {exc}")
            errors.append(feed["name"])

    articles.sort(key=lambda item: item.get("published_at") or "", reverse=True)
    articles = articles[:MAX_TOTAL]
    # Si tous les flux échouent, préserver les dernières données publiées plutôt que vider le site.
    if not articles and OUT.exists():
        old = json.loads(OUT.read_text(encoding="utf-8"))
        old["note"] = "La collecte a échoué pour tous les flux. Les articles affichés proviennent de la dernière collecte réussie."
        old["last_attempt"] = datetime.now(timezone.utc).isoformat()
        OUT.write_text(json.dumps(old, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Aucun flux récupéré : les données précédentes sont conservées.")
        return

    now = datetime.now(timezone.utc).isoformat()
    data = {
        "last_updated": now,
        "last_attempt": now,
        "timezone": "UTC; affichage en heure de Paris dans le navigateur",
        "article_count": len(articles),
        "sources_configured": len(FEEDS),
        "sources_with_errors": errors,
        "note": ("Certains flux n’ont pas répondu lors de cette collecte : " + ", ".join(errors) + ". La sélection peut donc être incomplète.") if errors else "",
        "articles": articles,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Collecte terminée : {len(articles)} articles, {len(errors)} flux en erreur.")

if __name__ == "__main__":
    main()
