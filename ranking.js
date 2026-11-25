/*
 * ActuSUP — classement des 20 actualités les plus importantes du mois (repli côté navigateur).
 *
 * Pendant de story_ranking.py : même tokenisation, même regroupement par histoire, même score et
 * même sélection avec diversité. Le collecteur (fetch_news.py) calcule normalement ce classement
 * avec l'archive des 30 jours ; ce module ne sert que si data/news.json n'en contient pas
 * (featured_news absent ou vide). Sans archive, il travaille sur les articles du fichier publié.
 * tests/test_parity.py vérifie que les constantes et les résultats restent alignés sur Python.
 */
(function (root) {
  "use strict";

  const WINDOW_DAYS = 30;
  const FEATURED_LIMIT = 20;
  const MAX_GAP_DAYS = 4;
  const JOIN_GROWTH = 0.04;
  const JOIN_THRESHOLD = 0.36;
  const MIN_SHARED_TERMS = 3;
  const ENTITY_BOOST = 1.6;
  const TITLE_WEIGHT = 2;
  const SUMMARY_CHARS = 320;
  const CENTROID_TERMS = 22;
  const CORE_TERMS = 14;
  const DAY_MS = 86400000;
  const HOUR_MS = 3600000;

  const STOPWORDS = new Set(("a au aux avec ce ces dans de des du elle elles en et eux il ils je la le les leur leurs lui ma mais me meme memes mes moi mon ne nos notre nous on ou par pas pour qu que quelle quelles quel quels qui sa sans se ses si son sont sous sur ta te tes toi ton toutes tout tres tu un une vos votre vous cela cette cet donc apres avant aussi alors ainsi autour autre autres avoir etre fait font faire fois selon entre depuis pendant durant chez via vers ici encore quand comme plus moins peu peut peuvent doit doivent annonce annoncent annoncee annoncees question questions sujet sujets actualite actualites information informations derniere dernier aujourd hui lundi mardi mercredi jeudi vendredi samedi dimanche france francais francaise francaises monde national nationale nationales europe europeen europeenne grande grands grand nouvelles nouvelle nouveaux nouveau premier premiere premiers premieres plusieurs chaque certains certaines notamment deja serait seraient devrait pourraient ete leurs autant contre bref video videos direct directes suivi suivent revenir revient voir voici voila suite cours jour jours semaine semaines matin soir nuit heures heure parmi partie parties ville villes pays presse media medias source sources article articles depeche franceinfo entier janvier fevrier mars avril mai juin juillet aout septembre octobre novembre decembre").split(" "));

  const SOURCE_PRIORITY = {
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
    "INA – La Revue des médias": 4
  };
  const OUTLET_FAMILY = { "France Info (Radio)": "Franceinfo (TV)", "RMC": "BFMTV" };

  const HARD_NEWS_TERMS = [
    "mort", "tue", "deces", "decede", "attentat", "attaque", "explosion", "seisme", "tremblement de terre",
    "guerre", "frappe", "bombardement", "cessez le feu", "otage", "accord", "sommet", "election", "scrutin",
    "demission", "demissionne", "motion de censure", "gouvernement", "premier ministre", "president",
    "assemblee nationale", "reforme", "budget", "greve", "proces", "condamne", "condamnation", "verdict",
    "perquisition", "garde a vue", "mis en examen", "incendie", "inondation", "tempete", "canicule",
    "crise", "krach", "faillite", "licenciement", "plan social", "record", "epidemie", "pandemie",
    "cyberattaque", "sanction", "tarif douanier", "nucleaire", "enquete", "inflation", "chomage",
    "tribunal", "cour de cassation", "conseil constitutionnel", "loi", "decret", "arrestation", "evacuation",
    "naufrage", "crash", "accident", "pompier", "secours", "disparition", "meurtre", "assassinat"
  ];
  const LOW_SIGNAL_TERMS = [
    "horoscope", "recette", "bon plan", "jeu concours", "quiz", "idee cadeau", "code promo", "promo", "soldes",
    "black friday", "tuto", "astuce", "que voir", "a voir", "ou regarder", "meilleurs", "meilleures",
    "top 10", "top 5", "people", "telerealite", "koh lanta", "star academy", "meteo du jour", "loto",
    "euromillions", "mot fleche", "sudoku", "newsletter", "podcast", "decouvrez", "on vous dit tout",
    "notre avis", "serie a regarder", "sortie cine", "bien etre", "beaute", "jardinage", "shopping",
    "partenariat", "sponsorise", "edito", "editorial", "tribune", "chronique", "revue de presse",
    "l info du jour", "l expresso", "top ou stop", "c est deja demain"
  ];
  const RECURRING_DATE_RE = /\b(?:lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\s+\d{1,2}(?:er)?\s+(?:janvier|fevrier|mars|avril|mai|juin|juillet|aout|septembre|octobre|novembre|decembre)\b/;
  const LIVE_PREFIX_RE = /^\s*(?:[^\p{L}\p{N}_«"“(]+\s*)?(?:en direct|direct|live|video|vidéo|podcast|diaporama|replay)\s*[:,.\-–—]\s*/iu;
  const NEUTRAL_CATEGORY = "Société";

  // ------------------------------------------------------------------ texte

  const APOSTROPHES = /[’‘ʼ´`]/g;

  function fold(text) {
    return String(text == null ? "" : text).replace(APOSTROPHES, "'")
      .normalize("NFKD").replace(/[^\x00-\x7f]/g, "").toLowerCase();
  }

  function stem(token) {
    if (token.length > 5 && token.endsWith("eaux")) return token.slice(0, -1);
    if (token.length > 4 && token.endsWith("aux")) return token.slice(0, -3) + "al";
    if (token.length > 4 && token.endsWith("s") && !token.endsWith("ss")) return token.slice(0, -1);
    return token;
  }

  function tokenize(text) {
    const out = [];
    for (const raw of fold(text).match(/[a-z0-9]{3,}/g) || []) {
      if (/^[0-9]+$/.test(raw)) continue;
      const token = stem(raw);
      if (token.length >= 3 && !STOPWORDS.has(token)) out.push(token);
    }
    const acronyms = String(text == null ? "" : text).match(/(?<![A-Za-zÀ-ÿ0-9])[A-Z]{2}(?![A-Za-zÀ-ÿ0-9])/g) || [];
    for (const acronym of acronyms) {
      const token = acronym.toLowerCase();
      if (!STOPWORDS.has(token)) out.push(token);
    }
    return out;
  }

  function isUpperWord(word) {
    return word === word.toUpperCase() && word !== word.toLowerCase();
  }

  function entityTerms(title) {
    const words = String(title == null ? "" : title).match(/\p{L}+(?:[’'-]\p{L}+)*/gu) || [];
    const found = new Set();
    words.forEach((word, index) => {
      if (index === 0 && !isUpperWord(word)) return;
      const first = Array.from(word)[0];
      if (first && first === first.toUpperCase() && first !== first.toLowerCase() && Array.from(word).length >= 2) {
        for (const part of word.split(/[’'-]/)) for (const token of tokenize(part)) found.add(token);
      }
    });
    return found;
  }

  function hasTerm(foldedTitle, terms) {
    const padded = " " + foldedTitle.replace(/[^a-z0-9]+/g, " ").trim() + " ";
    let hits = 0;
    for (const term of terms) {
      if (padded.includes(` ${term} `) || padded.includes(` ${term}s `) || padded.includes(` ${term}e `)) hits += 1;
    }
    return hits;
  }

  function capitalizeFirst(text) {
    const chars = Array.from(text);
    return chars.length ? chars[0].toUpperCase() + chars.slice(1).join("") : text;
  }

  function cleanHeadline(title) {
    let result = String(title == null ? "" : title).trim();
    const cleaned = result.replace(LIVE_PREFIX_RE, "").replace(/^[^\p{L}\p{N}_«"“(]+/u, "").trim();
    if (Array.from(cleaned).length >= 20) result = cleaned;
    return capitalizeFirst(result);
  }

  // ------------------------------------------------------------------ dates / médias

  const parisFormatter = (() => {
    try {
      return new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Paris", year: "numeric", month: "2-digit", day: "2-digit" });
    } catch (error) {
      return null;
    }
  })();

  function parisDay(ms) {
    if (parisFormatter) return parisFormatter.format(new Date(ms));
    return new Date(ms + HOUR_MS).toISOString().slice(0, 10);
  }

  function parseDate(value) {
    if (!value) return null;
    const ms = Date.parse(value);
    return Number.isFinite(ms) ? ms : null;
  }

  function outletKey(name) {
    const clean = String(name == null ? "" : name).trim();
    return Object.prototype.hasOwnProperty.call(OUTLET_FAMILY, clean) ? OUTLET_FAMILY[clean] : clean;
  }

  function outletWeight(name) {
    const clean = String(name == null ? "" : name).trim();
    if (!Object.prototype.hasOwnProperty.call(SOURCE_PRIORITY, clean)) return 0.6;
    return 0.5 + 0.5 * (SOURCE_PRIORITY[clean] - 4) / 5;
  }

  // ------------------------------------------------------------------ vecteurs

  function articleFeatures(article) {
    const title = String(article.title == null ? "" : article.title).trim();
    const published = parseDate(article.published_at);
    const source = String(article.source == null ? "" : article.source).trim();
    if (!title || published === null || !source) return null;
    const tf = new Map();
    for (const token of tokenize(title)) tf.set(token, (tf.get(token) || 0) + TITLE_WEIGHT);
    for (const token of tokenize(String(article.summary == null ? "" : article.summary).slice(0, SUMMARY_CHARS))) {
      tf.set(token, (tf.get(token) || 0) + 1);
    }
    if (!tf.size) return null;
    const outlets = new Set([outletKey(source)]);
    for (const name of Array.isArray(article.coverage_sources) ? article.coverage_sources : []) {
      if (typeof name === "string" && name.trim()) outlets.add(outletKey(name));
    }
    const rawMentions = String(article.mention_count == null ? "1" : article.mention_count);
    return {
      article, dt: published, tf, ent: entityTerms(title), folded: fold(title), outlets,
      mentions: /^[0-9]+$/.test(rawMentions) ? Math.max(1, parseInt(rawMentions, 10)) : 1
    };
  }

  function idfTable(documents) {
    const df = new Map();
    let count = 0;
    for (const terms of documents) {
      count += 1;
      for (const term of terms) df.set(term, (df.get(term) || 0) + 1);
    }
    const idf = new Map();
    for (const [term, freq] of df) idf.set(term, Math.log(1 + (count + 1) / (freq + 1)));
    return idf;
  }

  function byWeightThenTerm(a, b) {
    return b[1] - a[1] || (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0);
  }

  function vector(tf, ents, idf, top = CORE_TERMS) {
    let entries = [];
    for (const [term, weight] of tf) {
      entries.push([term, weight * (idf.has(term) ? idf.get(term) : 1) * (ents.has(term) ? ENTITY_BOOST : 1)]);
    }
    if (entries.length > top) entries = entries.sort(byWeightThenTerm).slice(0, top);
    return new Map(entries);
  }

  function norm(vec) {
    let sum = 0;
    for (const weight of vec.values()) sum += weight * weight;
    return Math.sqrt(sum);
  }

  function cosine(a, b, na, nb) {
    if (a.size > b.size) { [a, b, na, nb] = [b, a, nb, na]; }
    let dot = 0, shared = 0;
    for (const [term, weight] of a) {
      const other = b.get(term);
      if (other) { dot += weight * other; shared += 1; }
    }
    if (!dot) return [0, 0];
    na = na === undefined ? norm(a) : na;
    nb = nb === undefined ? norm(b) : nb;
    return [na && nb ? dot / (na * nb) : 0, shared];
  }

  // ------------------------------------------------------------------ sujets

  function round(value, digits) {
    const factor = 10 ** digits;
    return Math.round(value * factor) / factor;
  }

  function representativeQuality(feat, similarity) {
    const article = feat.article;
    const summaryLen = Math.min(String(article.summary || "").length, 260) / 260;
    const priority = (Object.prototype.hasOwnProperty.call(SOURCE_PRIORITY, article.source) ? SOURCE_PRIORITY[article.source] : 5) / 9;
    const title = String(article.title || "");
    const prefixPenalty = LIVE_PREFIX_RE.test(title) ? 0.25 : 0;
    const lengthPenalty = title.length > 160 || title.length < 45 ? 0.2 : 0;
    return round(1.5 * similarity + 0.5 * summaryLen + 0.5 * priority - prefixPenalty - lengthPenalty, 4);
  }

  function repRecord(article, quality) {
    return {
      id: String(article.id || ""),
      title: String(article.title || "").slice(0, 240),
      summary: String(article.summary || "").slice(0, 200),
      source: String(article.source || ""),
      feed_rank: article.feed_rank === undefined ? null : article.feed_rank,
      url: String(article.url || ""),
      published_at: article.published_at,
      category: article.category || NEUTRAL_CATEGORY,
      q: quality
    };
  }

  function newStory(feat) {
    const article = feat.article;
    return {
      id: String(article.id || "") || String(article.url || article.title),
      k: new Map(), e: new Set(), o: new Set(), m: 0, d: new Set(), f: feat.dt, l: feat.dt,
      fp: new Set(), c: new Map(), hs: 0, ls: 0, rep: repRecord(article, -9)
    };
  }

  function absorb(story, feat, similarity) {
    const article = feat.article;
    for (const [term, weight] of feat.tf) story.k.set(term, (story.k.get(term) || 0) + weight);
    for (const term of feat.ent) story.e.add(term);
    if (story.k.size > CENTROID_TERMS + 8) {
      const keep = Array.from(story.k.entries()).sort(byWeightThenTerm).slice(0, CENTROID_TERMS);
      story.k = new Map(keep);
      story.e = new Set(Array.from(story.e).filter(term => story.k.has(term)));
    }
    for (const name of feat.outlets) story.o.add(name);
    story.m += feat.mentions;
    story.d.add(parisDay(feat.dt));
    story.f = Math.min(story.f, feat.dt);
    story.l = Math.max(story.l, feat.dt);
    if (Number.isInteger(article.feed_rank) && article.feed_rank <= 3) story.fp.add(outletKey(article.source));
    const category = article.category || NEUTRAL_CATEGORY;
    story.c.set(category, (story.c.get(category) || 0) + 1);
    if (hasTerm(feat.folded, HARD_NEWS_TERMS)) story.hs += 1;
    if (hasTerm(feat.folded, LOW_SIGNAL_TERMS) || RECURRING_DATE_RE.test(feat.folded)) story.ls += 1;
    const quality = representativeQuality(feat, similarity);
    if (quality > story.rep.q) story.rep = repRecord(article, quality);
  }

  function joinThreshold(story) {
    return JOIN_THRESHOLD + JOIN_GROWTH * Math.log2(1 + Math.max(1, story.m || 1) / 10);
  }

  function updateStories(articles, now) {
    const windowStart = now - WINDOW_DAYS * DAY_MS;
    const feats = [];
    for (const article of Array.isArray(articles) ? articles : []) {
      if (!article || typeof article !== "object") continue;
      const feat = articleFeatures(article);
      if (feat && feat.dt >= windowStart && feat.dt <= now + 10 * 60000) feats.push(feat);
    }
    const idOf = feat => String(feat.article.id || "");
    feats.sort((a, b) => a.dt - b.dt || (idOf(a) < idOf(b) ? -1 : idOf(a) > idOf(b) ? 1 : 0));

    const batch = new Map();
    const unique = [];
    for (const feat of feats) {
      const id = idOf(feat);
      if (id && batch.has(id)) {
        for (const name of feat.outlets) batch.get(id).outlets.add(name);
        continue;
      }
      if (id) batch.set(id, feat);
      unique.push(feat);
    }
    if (!unique.length) return [];

    const stories = [];
    const idf = idfTable(unique.map(feat => feat.tf.keys()));
    const vectors = new Map();
    const index = new Map();
    const storyVector = i => {
      if (!vectors.has(i)) {
        const vec = vector(stories[i].k, stories[i].e, idf);
        vectors.set(i, [vec, norm(vec)]);
      }
      return vectors.get(i);
    };
    const indexStory = i => {
      for (const term of stories[i].k.keys()) {
        if (!index.has(term)) index.set(term, new Set());
        index.get(term).add(i);
      }
    };

    const gap = MAX_GAP_DAYS * DAY_MS;
    for (const feat of unique) {
      const vec = vector(feat.tf, feat.ent, idf);
      const vecNorm = norm(vec);
      const hits = new Map();
      for (const term of feat.tf.keys()) {
        for (const i of index.get(term) || []) hits.set(i, (hits.get(i) || 0) + 1);
      }
      let best = null, bestSim = 0;
      const candidates = Array.from(hits.entries()).filter(([, n]) => n >= MIN_SHARED_TERMS).map(([i]) => i).sort((a, b) => a - b);
      for (const i of candidates) {
        const story = stories[i];
        if (feat.dt - story.l > gap || story.f - feat.dt > gap) continue;
        const [svec, snorm] = storyVector(i);
        const [sim, shared] = cosine(vec, svec, vecNorm, snorm);
        if (shared >= MIN_SHARED_TERMS && sim > bestSim && sim >= joinThreshold(story)) { best = i; bestSim = sim; }
      }
      if (best !== null) {
        absorb(stories[best], feat, bestSim);
        vectors.delete(best);
        indexStory(best);
      } else {
        stories.push(newStory(feat));
        absorb(stories[stories.length - 1], feat, 0.5);
        indexStory(stories.length - 1);
      }
    }
    return stories;
  }

  // ------------------------------------------------------------------ score & sélection

  function storyCategory(story) {
    if (!story.c.size) return story.rep.category || NEUTRAL_CATEGORY;
    const repCategory = story.rep.category;
    let best = null;
    for (const [category, count] of story.c) {
      const key = [count, category === repCategory ? 1 : 0, category];
      if (best === null || key[0] > best[0] || (key[0] === best[0] && (key[1] > best[1] || (key[1] === best[1] && key[2] > best[2])))) best = key;
    }
    return best[2];
  }

  function scoreStory(story, now) {
    let weights = 0;
    for (const name of story.o) weights += outletWeight(name);
    const breadth = Math.log2(1 + weights);
    const persistence = Math.log2(1 + Math.max(1, story.d.size));
    const mentions = Math.max(1, story.m || 1);
    const volume = Math.log2(1 + mentions);
    const frontpage = Math.log2(1 + story.fp.size);
    const hard = Math.min(1, story.hs / mentions);
    const low = Math.min(1, story.ls / mentions);
    const ageDays = Math.max(0, (now - story.l) / DAY_MS);
    const recency = 0.6 + 0.4 * Math.pow(0.5, ageDays / 12);
    const raw = 3.2 * breadth + 1.5 * persistence + 0.6 * volume + 1.3 * frontpage + 2 * hard;
    return round(raw * recency * (1 - 0.65 * low), 4);
  }

  function qualifies(story) {
    return story.o.size >= 3 || (story.o.size >= 2 && story.d.size >= 2);
  }

  function selectTopStories(stories, now, limit = FEATURED_LIMIT, categoryPenalty = 0.86, categoryCap = 6, overlapPenalty = 0.7) {
    const windowStart = now - WINDOW_DAYS * DAY_MS;
    const pool = [];
    for (const story of stories) {
      if (story.l < windowStart) continue;
      pool.push({ story, score: scoreStory(story, now), category: storyCategory(story) });
    }
    const qualified = pool.filter(p => qualifies(p.story));
    if (qualified.length < limit) {
      const rest = pool.filter(p => !qualified.includes(p)).sort((a, b) => b.score - a.score);
      qualified.push(...rest.slice(0, limit - qualified.length));
    }
    const idf = idfTable(pool.map(p => p.story.k.keys()));
    for (const p of qualified) p.vec = vector(p.story.k, p.story.e, idf);

    const byIdThenScore = (a, b) => b.score - a.score || (a.story.id < b.story.id ? -1 : a.story.id > b.story.id ? 1 : 0);
    const chosen = [];
    const counts = new Map();
    let remaining = qualified.slice().sort(byIdThenScore);
    const overlapWith = p => chosen.reduce((max, c) => Math.max(max, cosine(p.vec, c.vec)[0]), 0);
    while (remaining.length && chosen.length < limit) {
      let best = null, bestValue = -1;
      for (const p of remaining) {
        const n = counts.get(p.category) || 0;
        if (n >= categoryCap && remaining.length > limit - chosen.length) continue;
        let value = p.score * Math.pow(categoryPenalty, n);
        if (chosen.length) {
          const overlap = overlapWith(p);
          if (overlap >= 0.55) continue;
          if (overlap >= 0.25) value *= 1 - overlapPenalty * overlap;
        }
        if (value > bestValue) { best = p; bestValue = value; }
      }
      if (best === null) {
        const relaxed = remaining.filter(p => !chosen.length || overlapWith(p) < 0.55);
        if (!relaxed.length) break;
        const valueOf = p => p.score * Math.pow(categoryPenalty, counts.get(p.category) || 0);
        best = relaxed.reduce((top, p) => {
          const a = valueOf(p), b = valueOf(top);
          return a > b || (a === b && p.story.id > top.story.id) ? p : top;
        });
      }
      chosen.push(best);
      counts.set(best.category, (counts.get(best.category) || 0) + 1);
      remaining = remaining.filter(p => p !== best);
    }
    return chosen.map(p => ({ story: p.story, score: p.score, category: p.category }));
  }

  function storyToFeatured(entry) {
    const { story, score, category } = entry;
    const rep = story.rep || {};
    const outlets = Array.from(story.o).sort((a, b) => {
      const pa = SOURCE_PRIORITY[a] || 0, pb = SOURCE_PRIORITY[b] || 0;
      const la = a.toLowerCase(), lb = b.toLowerCase();
      return pb - pa || (la < lb ? -1 : la > lb ? 1 : 0);
    });
    const item = {};
    for (const key of ["id", "title", "summary", "source", "feed_rank", "url", "published_at"]) item[key] = rep[key];
    item.title = cleanHeadline(item.title);
    item.category = category;
    item.coverage_sources = outlets;
    item.coverage_count = outlets.length;
    item.mention_count = Math.max(1, story.m || 1);
    item.importance_score = round(score, 3);
    item.latest_coverage_at = new Date(story.l).toISOString();
    item.first_coverage_at = new Date(story.f).toISOString();
    item.active_days = story.d.size;
    return item;
  }

  function buildMonthlyTop(articles, now = Date.now(), limit = FEATURED_LIMIT) {
    return selectTopStories(updateStories(articles, now), now, limit).map(storyToFeatured);
  }

  const api = {
    constants: {
      WINDOW_DAYS, FEATURED_LIMIT, MAX_GAP_DAYS, JOIN_GROWTH, JOIN_THRESHOLD, MIN_SHARED_TERMS, ENTITY_BOOST,
      TITLE_WEIGHT, SUMMARY_CHARS, CENTROID_TERMS, CORE_TERMS
    },
    STOPWORDS: Array.from(STOPWORDS), SOURCE_PRIORITY, OUTLET_FAMILY, HARD_NEWS_TERMS, LOW_SIGNAL_TERMS,
    fold, tokenize, entityTerms, cleanHeadline, outletKey, outletWeight, parisDay,
    updateStories, scoreStory, selectTopStories, storyToFeatured, buildMonthlyTop
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.ActuSUPRanking = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
