#!/usr/bin/env python3
"""Regroupement des articles en sujets et classement des actualités les plus importantes du mois.

Ce module ne dépend que de la bibliothèque standard : il est utilisé par ``fetch_news.py``
au moment de la collecte et testé de façon autonome (``python3 -m unittest discover tests``).
Le fichier ``ranking.js`` en est le pendant côté navigateur (repli lorsque ``featured_news``
est absent du JSON) ; ``tests/test_parity.py`` vérifie que les constantes restent alignées.

Principe
--------
1. Chaque article est transformé en vecteur de termes (titre pondéré x2, début du résumé,
   noms propres et sigles renforcés, pondération IDF).
2. Les articles sont rattachés, dans l'ordre chronologique, au sujet existant dont le
   « centroïde » leur ressemble le plus (similarité cosinus) à condition que ce sujet ait été
   couvert dans les ``MAX_GAP_DAYS`` derniers jours ; sinon un nouveau sujet est créé. Contrairement à un
   regroupement par chaînage, un article ne peut pas relier deux sujets distincts.
3. Chaque sujet reçoit un score d'importance : étendue (médias distincts, pondérés),
   persistance (nombre de jours de couverture), volume, présence en tête des flux,
   signaux éditoriaux (vocabulaire d'actualité « dure » ou de contenu de confort/promotion),
   décroissance de fraîcheur douce.
4. Les 20 sujets sont choisis par sélection gloutonne avec pénalité de diversité
   (catégorie déjà représentée, sujet proche d'un sujet déjà retenu).

Les sujets (``stories``) sont des dictionnaires JSON compacts : ils peuvent être conservés
d'une collecte à l'autre (``data/story_archive.json``) pour mesurer la persistance sur 30 jours.
"""
from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from datetime import datetime, timedelta, timezone

try:  # Heure de Paris pour compter les « jours de couverture » ; repli sur UTC+1 si tzdata absent.
    from zoneinfo import ZoneInfo
    _PARIS = ZoneInfo("Europe/Paris")
except Exception:  # pragma: no cover - dépend de l'environnement
    _PARIS = timezone(timedelta(hours=1))

WINDOW_DAYS = 30
FEATURED_LIMIT = 20
MAX_GAP_DAYS = 4            # un sujet « s'éteint » après 4 jours sans nouvel article
JOIN_GROWTH = 0.04
JOIN_THRESHOLD = 0.36       # similarité cosinus minimale pour rattacher un article à un sujet
MIN_SHARED_TERMS = 3
ENTITY_BOOST = 1.6
TITLE_WEIGHT = 2
SUMMARY_CHARS = 320
CENTROID_TERMS = 22
CORE_TERMS = 14
FRESH_HOURS = 4             # un article isolé n'est conservé que 4 h, le temps qu'un second média le rejoigne
SEEN_HOURS = 12             # identifiants d'articles mémorisés : évite de compter deux fois un article revu
SINCE_MARGIN_HOURS = 6      # à chaque collecte, seuls les articles publiés depuis la précédente (- 6 h) sont examinés

# Mots fonctionnels et termes trop génériques pour rapprocher deux actualités.
STOPWORDS = set("""
a au aux avec ce ces dans de des du elle elles en et eux il ils je la le les leur leurs lui ma mais me meme memes mes moi mon ne nos notre nous on ou par pas pour qu que quelle quelles quel quels qui sa sans se ses si son sont sous sur ta te tes toi ton toutes tout tres tu un une vos votre vous cela cette cet donc apres avant aussi alors ainsi autour autre autres avoir etre fait font faire fois selon entre depuis pendant durant chez via vers ici encore quand comme plus moins peu peut peuvent doit doivent annonce annoncent annoncee annoncees question questions sujet sujets actualite actualites information informations derniere dernier aujourd hui lundi mardi mercredi jeudi vendredi samedi dimanche france francais francaise francaises monde national nationale nationales europe europeen europeenne grande grands grand nouvelles nouvelle nouveaux nouveau premier premiere premiers premieres plusieurs chaque certains certaines notamment deja serait seraient devrait pourraient ete leurs autant contre bref video videos direct directes suivi suivent revenir revient voir voici voila suite cours jour jours semaine semaines matin soir nuit heures heure parmi partie parties ville villes pays presse media medias source sources article articles depeche franceinfo entier janvier fevrier mars avril mai juin juillet aout septembre octobre novembre decembre
""".split())

# Médias et poids éditorial (4 = média spécialisé, 9 = référence nationale généraliste).
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

# Deux marques qui reprennent la même rédaction ne comptent que pour un seul média.
OUTLET_FAMILY = {"France Info (Radio)": "Franceinfo (TV)", "RMC": "BFMTV"}

# Signaux éditoriaux, appliqués sur le titre (mots entiers, sans accents ni pluriels).
HARD_NEWS_TERMS = [
    "mort", "tue", "deces", "decede", "attentat", "attaque", "explosion", "seisme", "tremblement de terre",
    "guerre", "frappe", "bombardement", "cessez le feu", "otage", "accord", "sommet", "election", "scrutin",
    "demission", "demissionne", "motion de censure", "gouvernement", "premier ministre", "president",
    "assemblee nationale", "reforme", "budget", "greve", "proces", "condamne", "condamnation", "verdict",
    "perquisition", "garde a vue", "mis en examen", "incendie", "inondation", "tempete", "canicule",
    "crise", "krach", "faillite", "licenciement", "plan social", "record", "epidemie", "pandemie",
    "cyberattaque", "sanction", "tarif douanier", "nucleaire", "enquete", "inflation", "chomage",
    "tribunal", "cour de cassation", "conseil constitutionnel", "loi", "decret", "arrestation", "evacuation",
    "naufrage", "crash", "accident", "pompier", "secours", "disparition", "meurtre", "assassinat",
]
LOW_SIGNAL_TERMS = [
    "horoscope", "recette", "bon plan", "jeu concours", "quiz", "idee cadeau", "code promo", "promo", "soldes",
    "black friday", "test", "tuto", "astuce", "que voir", "a voir", "ou regarder", "meilleurs", "meilleures",
    "selection", "classement des", "top 10", "top 5", "people", "telerealite", "koh lanta", "star academy",
    "meteo du jour", "tirage", "loto", "euromillions", "mot fleche", "sudoku", "newsletter", "podcast",
    "decouvrez", "on vous dit tout", "notre avis", "critique", "serie a regarder", "ce week end", "sortie ciné",
    "bien etre", "mode", "beaute", "deco", "voyage", "jardinage", "shopping", "partenariat", "sponsorise",
    "edito", "editorial", "tribune", "chronique", "revue de presse", "l info du jour", "l expresso", "top ou stop",
    "c est deja demain", "bonjour", "invite de", "temoignage",
]
# Rubriques récurrentes datées (« du jeudi 19 novembre 2026 ») : contenu de flux, pas un événement.
RECURRING_DATE_RE = re.compile(
    r"\b(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+\d{1,2}(?:er)?\s+"
    r"(?:janvier|fevrier|mars|avril|mai|juin|juillet|aout|septembre|octobre|novembre|decembre)\b")
LIVE_PREFIX_RE = re.compile(r"^\s*(?:[^\w«\"“(]+\s*)?(?:en direct|direct|live|video|vidéo|podcast|diaporama|replay)\s*[:,.\-–—]\s*", re.I)

CATEGORIES_NEUTRAL = "Société"


# --------------------------------------------------------------------------- texte


_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "ʼ": "'", "´": "'", "`": "'"})


def fold(text: str) -> str:
    """Minuscules sans accents ; les apostrophes typographiques valent l'apostrophe droite (l’Élysée = l'Élysée)."""
    return unicodedata.normalize("NFKD", str(text or "").translate(_APOSTROPHES)).encode("ascii", "ignore").decode("ascii").lower()


def stem(token: str) -> str:
    """Normalisation légère du pluriel français, sans dépendance externe."""
    if len(token) > 5 and token.endswith("eaux"):
        return token[:-1]
    if len(token) > 4 and token.endswith("aux"):
        return token[:-3] + "al"
    if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


_ACRONYM_RE = re.compile(r"(?<![A-Za-zÀ-ÿ0-9])[A-Z]{2}(?![A-Za-zÀ-ÿ0-9])")


def tokenize(text: str) -> list[str]:
    """Termes significatifs (ASCII, minuscules, sans mots vides ni nombres).

    Les sigles de deux lettres écrits en capitales (RN, UE, PS, LR…) sont conservés : ils désignent
    souvent l'acteur central d'une actualité politique.
    """
    out = []
    for token in re.findall(r"[a-z0-9]{3,}", fold(text)):
        if token.isdigit():
            continue
        token = stem(token)
        if len(token) >= 3 and token not in STOPWORDS:
            out.append(token)
    for acronym in _ACRONYM_RE.findall(str(text or "")):
        token = acronym.lower()
        if token not in STOPWORDS:
            out.append(token)
    return out


def entity_terms(title: str) -> set[str]:
    """Noms propres et sigles : mots capitalisés qui ne sont pas le premier mot du titre."""
    words = re.findall(r"[^\W\d_]+(?:[’'-][^\W\d_]+)*", str(title or ""), re.UNICODE)
    found = set()
    for index, word in enumerate(words):
        if index == 0 and not word.isupper():
            continue
        if word[:1].isupper() and len(word) >= 2:
            for part in re.split(r"[’'-]", word):
                for token in tokenize(part):
                    found.add(token)
    return found


def has_term(folded_title: str, terms) -> int:
    """Nombre de termes (mots entiers ou expressions) trouvés dans un titre déjà « foldé »."""
    padded = " " + re.sub(r"[^a-z0-9]+", " ", folded_title).strip() + " "
    hits = 0
    for term in terms:
        if f" {term} " in padded or f" {term}s " in padded or f" {term}e " in padded:
            hits += 1
    return hits


def clean_headline(title: str) -> str:
    """Retire les préfixes éditoriaux (« EN DIRECT, », « VIDÉO : », puces emoji) d'un titre affiché."""
    title = str(title or "").strip()
    cleaned = LIVE_PREFIX_RE.sub("", title)
    cleaned = re.sub(r"^[^\w«\"“(]+", "", cleaned).strip()
    if len(cleaned) >= 20:
        title = cleaned
    return title[:1].upper() + title[1:] if title else title


# --------------------------------------------------------------------------- dates / médias


def parse_dt(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def paris_day(dt: datetime) -> str:
    return dt.astimezone(_PARIS).strftime("%Y-%m-%d")


def outlet_key(name: str) -> str:
    name = str(name or "").strip()
    return OUTLET_FAMILY.get(name, name)


def outlet_weight(name: str) -> float:
    """0,5 (média spécialisé) à 1,0 (référence généraliste) ; 0,6 pour un média inconnu."""
    priority = SOURCE_PRIORITY.get(str(name or "").strip())
    if priority is None:
        return 0.6
    return 0.5 + 0.5 * (priority - 4) / 5


# --------------------------------------------------------------------------- vecteurs


def article_features(article: dict) -> dict | None:
    title = str(article.get("title") or "").strip()
    published = parse_dt(article.get("published_at"))
    source = str(article.get("source") or "").strip()
    if not title or not published or not source:
        return None
    tf: dict[str, int] = {}
    for token in tokenize(title):
        tf[token] = tf.get(token, 0) + TITLE_WEIGHT
    for token in tokenize(str(article.get("summary") or "")[:SUMMARY_CHARS]):
        tf[token] = tf.get(token, 0) + 1
    if not tf:
        return None
    return {
        "article": article,
        "dt": published,
        "tf": tf,
        "ent": entity_terms(title),
        "folded": fold(title),
        "outlets": {outlet_key(source)} | {
            outlet_key(name) for name in (article.get("coverage_sources") or [])
            if isinstance(name, str) and name.strip()
        },
        "mentions": max(1, int(article.get("mention_count") or 1)) if str(article.get("mention_count") or "1").isdigit() else 1,
    }


def _idf_table(documents) -> dict[str, float]:
    df: dict[str, int] = {}
    count = 0
    for terms in documents:
        count += 1
        for term in terms:
            df[term] = df.get(term, 0) + 1
    return {term: math.log(1.0 + (count + 1.0) / (freq + 1.0)) for term, freq in df.items()}


def _vector(tf: dict, ents, idf: dict, top: int = CORE_TERMS) -> dict:
    """Vecteur TF-IDF réduit aux ``top`` termes les plus lourds : l'identité du sujet, sans le bruit."""
    weighted = {
        term: weight * idf.get(term, 1.0) * (ENTITY_BOOST if term in ents else 1.0)
        for term, weight in tf.items()
    }
    if len(weighted) > top:
        weighted = dict(sorted(weighted.items(), key=lambda kv: (-kv[1], kv[0]))[:top])
    return weighted


def _norm(vector: dict) -> float:
    return math.sqrt(sum(w * w for w in vector.values()))


def _cosine(a: dict, b: dict, na: float | None = None, nb: float | None = None) -> tuple[float, int]:
    """Similarité cosinus et nombre de termes communs (les normes peuvent être fournies pré-calculées)."""
    if len(a) > len(b):
        a, b, na, nb = b, a, nb, na
    dot, shared = 0.0, 0
    for term, weight in a.items():
        other = b.get(term)
        if other:
            dot += weight * other
            shared += 1
    if not dot:
        return 0.0, 0
    na = _norm(a) if na is None else na
    nb = _norm(b) if nb is None else nb
    return (dot / (na * nb) if na and nb else 0.0), shared


# --------------------------------------------------------------------------- sujets


def representative_quality(feat: dict, similarity: float) -> float:
    """Choisit le titre affiché : proche du cœur du sujet, informatif, d'un média de référence."""
    article = feat["article"]
    summary_len = min(len(str(article.get("summary") or "")), 260) / 260
    priority = SOURCE_PRIORITY.get(str(article.get("source") or ""), 5) / 9
    title = str(article.get("title") or "")
    prefix_penalty = 0.25 if LIVE_PREFIX_RE.match(title) else 0.0
    length_penalty = 0.2 if len(title) > 160 or len(title) < 45 else 0.0
    return round(1.5 * similarity + 0.5 * summary_len + 0.5 * priority - prefix_penalty - length_penalty, 4)


def _rep_record(article: dict, quality: float) -> dict:
    return {
        "id": str(article.get("id") or ""),
        "title": str(article.get("title") or "")[:240],
        "summary": str(article.get("summary") or "")[:200],
        "source": str(article.get("source") or ""),
        "feed_rank": article.get("feed_rank"),
        "url": str(article.get("url") or ""),
        "published_at": article.get("published_at"),
        "category": article.get("category") or CATEGORIES_NEUTRAL,
        "q": quality,
    }


def _new_story(feat: dict, similarity: float = 1.0) -> dict:
    article = feat["article"]
    story = {
        "id": hashlib.sha1(str(article.get("id") or article.get("url") or article.get("title")).encode()).hexdigest()[:12],
        "k": {},
        "e": [],
        "o": [],
        "m": 0,
        "d": [],
        "f": feat["dt"].isoformat(),
        "l": feat["dt"].isoformat(),
        "fp": [],
        "c": {},
        "hs": 0,
        "ls": 0,
        "rep": _rep_record(article, -9.0),
    }
    return story


def _absorb(story: dict, feat: dict, similarity: float) -> None:
    article = feat["article"]
    for term, weight in feat["tf"].items():
        story["k"][term] = story["k"].get(term, 0) + weight
    story["e"] = sorted(set(story["e"]) | feat["ent"])
    if len(story["k"]) > CENTROID_TERMS + 8:
        keep = sorted(story["k"].items(), key=lambda kv: (-kv[1], kv[0]))[:CENTROID_TERMS]
        story["k"] = dict(keep)
        story["e"] = [term for term in story["e"] if term in story["k"]]
    story["o"] = sorted(set(story["o"]) | feat["outlets"])
    story["m"] += feat["mentions"]
    story["d"] = sorted(set(story["d"]) | {paris_day(feat["dt"])})
    iso = feat["dt"].isoformat()
    story["f"] = min(story["f"], iso, key=lambda v: parse_dt(v))
    story["l"] = max(story["l"], iso, key=lambda v: parse_dt(v))
    rank = article.get("feed_rank")
    if isinstance(rank, int) and rank <= 3:
        story["fp"] = sorted(set(story["fp"]) | {outlet_key(article.get("source"))})
    category = article.get("category") or CATEGORIES_NEUTRAL
    story["c"][category] = story["c"].get(category, 0) + 1
    story["hs"] += 1 if has_term(feat["folded"], HARD_NEWS_TERMS) else 0
    story["ls"] += 1 if (has_term(feat["folded"], LOW_SIGNAL_TERMS) or RECURRING_DATE_RE.search(feat["folded"])) else 0
    quality = representative_quality(feat, similarity)
    if quality > story["rep"].get("q", -9.0):
        story["rep"] = _rep_record(article, quality)


def join_threshold(story: dict) -> float:
    """Plus un sujet est gros, plus il est exigeant : évite que quelques mots-clés fédèrent tout un thème."""
    return JOIN_THRESHOLD + JOIN_GROWTH * math.log2(1.0 + int(story.get("m") or 1) / 10.0)


def update_stories(stories: list[dict], articles: list[dict], now: datetime,
                   skip_ids: set | None = None, since: datetime | None = None) -> list[dict]:
    """Rattache ``articles`` aux ``stories`` existantes (ou en crée) et retire celles de plus de 30 jours.

    ``skip_ids`` : identifiants d'articles déjà comptés (collectes précédentes) ; ``since`` : les
    articles publiés avant cette date ont déjà été examinés. La fonction est déterministe ; un
    article présent deux fois dans le lot (même ``id``) n'est compté qu'une fois, ses médias
    supplémentaires étant fusionnés.
    """
    window_start = now - timedelta(days=WINDOW_DAYS)
    stories = [dict(story) for story in stories if isinstance(story, dict) and story.get("k")]
    for story in stories:
        story["k"] = dict(story["k"])
        story["c"] = dict(story.get("c") or {})
        story["rep"] = dict(story.get("rep") or {})
    stories = [s for s in stories if (parse_dt(s.get("l")) or window_start) >= window_start]

    feats = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        feat = article_features(article)
        if feat and window_start <= feat["dt"] <= now + timedelta(minutes=10) and (since is None or feat["dt"] >= since):
            feats.append(feat)
    feats.sort(key=lambda f: (f["dt"], str(f["article"].get("id") or "")))

    skip_ids = skip_ids or set()
    batch: dict[str, dict] = {}
    unique = []
    for feat in feats:
        article_id = str(feat["article"].get("id") or "")
        if article_id and article_id in skip_ids:
            continue
        if article_id and article_id in batch:
            batch[article_id]["outlets"] = batch[article_id]["outlets"] | feat["outlets"]
            continue
        if article_id:
            batch[article_id] = feat
        unique.append(feat)
    feats = unique
    if not feats:
        return stories

    idf = _idf_table(
        [set(f["tf"]) for f in feats] + [set(s["k"]) for s in stories]
    )
    vectors: dict[int, tuple[dict, float]] = {}
    index: dict[str, set[int]] = {}

    def story_vector(i):
        if i not in vectors:
            vec = _vector(stories[i]["k"], set(stories[i]["e"]), idf)
            vectors[i] = (vec, _norm(vec))
        return vectors[i]

    def index_story(i):
        for term in stories[i]["k"]:
            index.setdefault(term, set()).add(i)

    for i in range(len(stories)):
        index_story(i)

    gap = timedelta(days=MAX_GAP_DAYS)
    for feat in feats:
        vec = _vector(feat["tf"], feat["ent"], idf)
        norm = _norm(vec)
        hits: dict[int, int] = {}
        for term in feat["tf"]:
            for i in index.get(term, ()):
                hits[i] = hits.get(i, 0) + 1
        best, best_sim = None, 0.0
        for i in sorted(i for i, n in hits.items() if n >= MIN_SHARED_TERMS):
            story = stories[i]
            last = parse_dt(story["l"])
            first = parse_dt(story["f"])
            if feat["dt"] - last > gap or first - feat["dt"] > gap:
                continue
            svec, snorm = story_vector(i)
            sim, shared = _cosine(vec, svec, norm, snorm)
            if shared >= MIN_SHARED_TERMS and sim > best_sim and sim >= join_threshold(story):
                best, best_sim = i, sim
        if best is not None:
            _absorb(stories[best], feat, best_sim)
            vectors.pop(best, None)
            index_story(best)
        else:
            stories.append(_new_story(feat))
            _absorb(stories[-1], feat, 0.5)  # le premier article ne « ressemble » pas encore au sujet
            index_story(len(stories) - 1)
    return stories


# --------------------------------------------------------------------------- archive


def update_archive(archive: dict | None, articles: list[dict], now: datetime) -> dict:
    """Met à jour l'archive ``{"updated_at", "seen" (id -> minute de publication), "stories"}`` avec les articles d'une collecte.

    Sans archive, tous les articles de la fenêtre de 30 jours sont examinés. Avec une archive, seuls
    ceux publiés depuis la collecte précédente (moins ``SINCE_MARGIN_HOURS``) le sont, et ``seen``
    mémorise les identifiants des 12 dernières heures pour ne compter chaque article qu'une fois.
    """
    archive = archive if isinstance(archive, dict) else {}
    previous = parse_dt(archive.get("updated_at"))
    since = previous - timedelta(hours=SINCE_MARGIN_HOURS) if previous and previous <= now else None
    # On garde les identifiants au moins aussi loin que « since », sinon un article publié entre
    # « since » et « maintenant - 12 h » (collecte précédente très ancienne) serait recompté.
    horizon = min(now - timedelta(hours=SEEN_HOURS), since or now)
    cutoff_minute = int(horizon.timestamp() // 60)
    seen = {
        str(i): int(minute) for i, minute in (archive.get("seen") or {}).items()
        if isinstance(minute, (int, float)) and minute >= cutoff_minute
    } if isinstance(archive.get("seen"), dict) else {}
    stories = update_stories(archive.get("stories") or [], articles, now, skip_ids=set(seen), since=since)
    for article in articles:
        if not isinstance(article, dict) or not article.get("id"):
            continue
        published = parse_dt(article.get("published_at"))
        if published and int(published.timestamp() // 60) >= cutoff_minute:
            seen[str(article["id"])] = int(published.timestamp() // 60)
    return {
        "version": 1,
        "updated_at": now.isoformat(),
        "seen": dict(sorted(seen.items())),
        "stories": prune_archive(stories, now),
    }


# --------------------------------------------------------------------------- score


def story_category(story: dict) -> str:
    counts = story.get("c") or {}
    if not counts:
        return story.get("rep", {}).get("category") or CATEGORIES_NEUTRAL
    rep_category = story.get("rep", {}).get("category")
    return max(counts, key=lambda c: (counts[c], c == rep_category, c))


def score_story(story: dict, now: datetime) -> float:
    outlets = story.get("o") or []
    breadth = math.log2(1.0 + sum(outlet_weight(name) for name in outlets))
    days = max(1, len(story.get("d") or []))
    persistence = math.log2(1.0 + days)
    volume = math.log2(1.0 + max(1, int(story.get("m") or 1)))
    frontpage = math.log2(1.0 + len(story.get("fp") or []))
    mentions = max(1, int(story.get("m") or 1))
    hard = min(1.0, (story.get("hs") or 0) / mentions)
    low = min(1.0, (story.get("ls") or 0) / mentions)
    last = parse_dt(story.get("l")) or now
    age_days = max(0.0, (now - last).total_seconds() / 86400)
    # Décroissance douce : un grand sujet du début du mois garde au moins 60 % de son poids.
    recency = 0.6 + 0.4 * 0.5 ** (age_days / 12.0)
    raw = 3.2 * breadth + 1.5 * persistence + 0.6 * volume + 1.3 * frontpage + 2.0 * hard
    return round(raw * recency * (1.0 - 0.65 * low), 4)


def _qualifies(story: dict) -> bool:
    outlets = len(story.get("o") or [])
    days = len(story.get("d") or [])
    return outlets >= 3 or (outlets >= 2 and days >= 2)


def select_top_stories(stories: list[dict], now: datetime, limit: int = FEATURED_LIMIT,
                       category_penalty: float = 0.86, category_cap: int = 6,
                       overlap_penalty: float = 0.7) -> list[dict]:
    """Sélection gloutonne avec diversité : catégories et sujets voisins sont pénalisés."""
    window_start = now - timedelta(days=WINDOW_DAYS)
    pool = []
    for story in stories:
        last = parse_dt(story.get("l"))
        if last is None or last < window_start:
            continue
        pool.append({"story": story, "score": score_story(story, now), "category": story_category(story)})
    qualified = [p for p in pool if _qualifies(p["story"])]
    # S'il y a trop peu de sujets recoupés (début de collecte), compléter avec les meilleurs restants.
    if len(qualified) < limit:
        rest = sorted((p for p in pool if p not in qualified), key=lambda p: -p["score"])
        qualified += rest[: limit - len(qualified)]

    idf = _idf_table([set(p["story"]["k"]) for p in pool])
    for p in qualified:
        p["vec"] = _vector(p["story"]["k"], set(p["story"].get("e") or []), idf)

    chosen: list[dict] = []
    counts: dict[str, int] = {}
    remaining = sorted(qualified, key=lambda p: (-p["score"], p["story"].get("id", "")))
    while remaining and len(chosen) < limit:
        best, best_value = None, -1.0
        for p in remaining:
            n = counts.get(p["category"], 0)
            if n >= category_cap and len(remaining) > limit - len(chosen):
                continue
            value = p["score"] * (category_penalty ** n)
            if chosen:
                overlap = max(_cosine(p["vec"], c["vec"])[0] for c in chosen)
                if overlap >= 0.55:
                    continue  # même sujet raconté par un autre regroupement
                if overlap >= 0.25:
                    value *= 1.0 - overlap_penalty * overlap
            if value > best_value:
                best, best_value = p, value
        if best is None:
            # Plus aucun sujet « dans les clous » : on relâche le plafond de catégorie pour atteindre 20.
            relaxed = [p for p in remaining if not chosen or max(_cosine(p["vec"], c["vec"])[0] for c in chosen) < 0.55]
            if not relaxed:
                break
            best = max(relaxed, key=lambda p: (p["score"] * (category_penalty ** counts.get(p["category"], 0)), p["story"].get("id", "")))
        chosen.append(best)
        counts[best["category"]] = counts.get(best["category"], 0) + 1
        remaining.remove(best)
    return [dict(p["story"], _score=p["score"], _category=p["category"]) for p in chosen]


def story_to_featured(story: dict) -> dict:
    """Format de ``featured_news`` : champs historiques de l'article + indicateurs de couverture."""
    rep = story.get("rep") or {}
    outlets = sorted(story.get("o") or [], key=lambda n: (-SOURCE_PRIORITY.get(n, 0), n.casefold()))
    item = {k: rep.get(k) for k in ("id", "title", "summary", "source", "feed_rank", "url", "published_at")}
    item["title"] = clean_headline(item["title"])
    item["category"] = story.get("_category") or story_category(story)
    item.update({
        "coverage_sources": outlets,
        "coverage_count": len(outlets),
        "mention_count": int(story.get("m") or 1),
        "importance_score": round(float(story.get("_score", 0.0)), 3),
        "latest_coverage_at": story.get("l"),
        "first_coverage_at": story.get("f"),
        "active_days": len(story.get("d") or []),
    })
    return item


def build_monthly_top(stories: list[dict], now: datetime, limit: int = FEATURED_LIMIT) -> list[dict]:
    return [story_to_featured(s) for s in select_top_stories(stories, now, limit)]


def prune_archive(stories: list[dict], now: datetime, max_stories: int = 360) -> list[dict]:
    """Réduit l'archive aux sujets utiles pour le classement du mois.

    Sont conservés : les ``max_stories`` sujets recoupés par au moins deux médias ayant le meilleur
    score, et les articles isolés des dernières heures (un second média peut encore les rejoindre).
    L'ordre de sortie (par identifiant) est stable pour limiter la taille des diffs Git.
    """
    window_start = now - timedelta(days=WINDOW_DAYS)
    fresh_cut = now - timedelta(hours=FRESH_HOURS)
    confirmed, fresh = [], []
    for story in stories:
        last = parse_dt(story.get("l"))
        if last is None or last < window_start:
            continue
        if len(story.get("o") or []) >= 2:
            confirmed.append(story)
        elif last >= fresh_cut:
            fresh.append(story)
    confirmed.sort(key=lambda s: (-score_story(s, now), s.get("id", "")))
    kept = confirmed[:max_stories] + fresh[:200]
    kept.sort(key=lambda s: s.get("id", ""))
    return kept
