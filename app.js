const DATA_URL = "data/news.json";
const PAGE_SIZE = 12;
const AUTO_REFRESH_INTERVAL = 10 * 60 * 1000;
let allNews = [];
let selectedCategory = "Toutes";
let visibleCount = PAGE_SIZE;
let lastLoadAttemptAt = Date.now();

const grid = document.querySelector("#news-grid");
const template = document.querySelector("#news-card-template");
const searchInput = document.querySelector("#search-input");
const sortSelect = document.querySelector("#sort-select");
const emptyState = document.querySelector("#empty-state");
const loadMore = document.querySelector("#load-more");
const resultCount = document.querySelector("#result-count");
const updateLabel = document.querySelector("#update-label");
const statusMessage = document.querySelector("#status-message");
const refreshButton = document.querySelector("#refresh-news");
const featuredGrid = document.querySelector("#top-stories-grid");
const featuredStart = document.querySelector("#top-stories-start");
const featuredEnd = document.querySelector("#top-stories-end");
const featuredMeta = document.querySelector("#top-stories-meta");
const featuredEmpty = document.querySelector("#top-stories-empty");
const featuredToggle = document.querySelector("#toggle-top-stories");
const featuredDetails = document.querySelector("#top-stories-details");

function formatDate(value) {
  if (!value) return "Date non précisée";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date non précisée";
  return new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short", year: "numeric" }).format(date);
}
function formatUpdated(value) {
  if (!value) return "Collecte pas encore effectuée";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Date de collecte indisponible";
  return `Dernière collecte : ${new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Paris" }).format(date)} · heure de Paris`;
}
function safeText(value, fallback = "") {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}
function formatShortDate(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "short", timeZone: "Europe/Paris" }).format(date);
}

// Le fil général ne conserve que les articles publiés au cours des 30 derniers jours.
function keepArticlesFromLast30Days(articles, now = Date.now()) {
  const cutoff = now - 30 * 24 * 60 * 60 * 1000;
  return articles.filter(item => {
    const publishedAt = Date.parse(item?.published_at || "");
    return Number.isFinite(publishedAt) && publishedAt >= cutoff && publishedAt <= now;
  });
}

// Compteurs recalculés à chaque chargement des données, à partir des articles récents.
function updateCategoryCounts() {
  const counts = new Map();
  allNews.forEach(item => {
    const category = safeText(item.category, "Actualité");
    counts.set(category, (counts.get(category) || 0) + 1);
  });

  document.querySelectorAll(".category-chip").forEach(button => {
    if (!button.dataset.categoryLabel) {
      button.dataset.categoryLabel = button.textContent.trim();
    }
    const category = button.dataset.category;
    const count = category === "Toutes" ? allNews.length : (counts.get(category) || 0);
    const label = button.dataset.categoryLabel;
    button.textContent = `${label} ${count}`;
    button.setAttribute("aria-label", `${label}, ${count} article${count === 1 ? "" : "s"}`);
  });
}

// Angles éditoriaux déterministes : une lecture stratégique et une piste créative,
// adaptées au sujet détecté dans le titre et le résumé de chaque article.
const COMMUNICATION_ANALYSIS_RULES = [
  {
    keywords: ["scandale", "controverse", "polemique", "boycott", "rappel de produit", "plainte contre", "mise en cause", "crise de reputation", "excuses publiques"],
    strategy: "Qualifier le niveau de risque, les publics directement touchés et les faits vérifiés avant de choisir le porte-parole, le canal et le calendrier de réponse.",
    creative: "Privilégier une prise de parole sobre et démontrable : chronologie, questions-réponses ou page de suivi. Éviter le slogan défensif, la surenchère émotionnelle et les promesses sans preuve."
  },
  {
    keywords: ["reseaux sociaux", "tiktok", "instagram", "facebook", "youtube", "meta ", "influenceur", "influenceuse", "plateforme", "algorithme", "moderation", "contenu viral", "createur de contenu"],
    strategy: "Distinguer portée, engagement qualifié et action réelle ; évaluer aussi la modération, la sécurité des communautés et la cohérence entre plateforme, cible et objectif.",
    creative: "Choisir un format natif au canal — démonstration vidéo, carrousel explicatif ou réponse publique — avec une accroche compréhensible sans contexte et une version adaptée à chaque plateforme."
  },
  {
    keywords: ["publicite", "campagne publicitaire", "marketing d'influence", "annonceur", "marque lance", "nouvelle campagne", "spot publicitaire", "sponsoring", "achat media"],
    strategy: "Relier objectif, public prioritaire, promesse et preuve ; définir un indicateur par étape du parcours pour ne pas confondre visibilité, mémorisation et conversion.",
    creative: "Construire un concept reconnaissable à partir d'une tension réelle du public, puis décliner la même idée en accroche, direction artistique et formats courts sans diluer la promesse."
  },
  {
    keywords: ["intelligence artificielle", "chatgpt", "openai", "anthropic", "modele d'ia", "modele de langage", "ia generative", "agent ia", "automatisation par ia"],
    strategy: "Définir l'usage autorisé, les données mobilisées, le niveau de validation humaine et la responsabilité éditoriale avant de généraliser l'outil.",
    creative: "Utiliser l'IA pour explorer des pistes, puis retravailler angle, voix de marque et références culturelles ; vérifier les visuels et signaler l'usage de l'outil lorsque cela influe sur la confiance."
  },
  {
    keywords: ["cyberattaque", "piratage", "ransomware", "rancongiciel", "fuite de donnees", "donnees personnelles volees", "cybersecurite", "incident informatique"],
    strategy: "Établir ce qui est confirmé, qui est concerné et quelles mesures sont engagées ; organiser une séquence de mises à jour sans minimiser l'incident ni promettre trop tôt.",
    creative: "Préparer un message d'alerte lisible, une FAQ mise à jour et une page de référence horodatée ; faire passer les consignes utiles avant le discours institutionnel."
  },
  {
    keywords: ["election", "elections", "presidentielle", "legislatives", "municipales", "scrutin", "vote", "candidat", "sondage", "urnes", "campagne electorale"],
    strategy: "Séparer données, projections et prises de position ; identifier les publics et les questions prioritaires sans traiter un sondage ou une déclaration comme un résultat acquis.",
    creative: "Rendre les enjeux comparables avec une chronologie, un graphique sourcé ou un format « qui propose quoi ? » ; maintenir une hiérarchie visuelle neutre et un vocabulaire non partisan."
  },
  {
    keywords: ["budget", "loi de finances", "deficit public", "depenses publiques", "impot", "taxe", "fiscalite", "finances publiques", "budget de l'etat"],
    strategy: "Traduire les arbitrages en conséquences par public — bénéficiaires, contribuables, services et partenaires — en distinguant montants annoncés, mesures votées et effets attendus.",
    creative: "Faire parler les chiffres avec un avant/après, une infographie ou des cas concrets ; afficher période, unité et source pour éviter les comparaisons trompeuses."
  },
  {
    keywords: ["manifestation", "manifestants", "mobilisation", "greve", "mouvement social", "syndicat", "syndicats", "blocage", "protestation", "revendications"],
    strategy: "Comparer le discours officiel à l'expérience vécue et aux revendications ; cartographier les parties prenantes et synchroniser communication interne, service client et parole publique.",
    creative: "Construire un format d'écoute et de clarification — FAQ, points d'étape ou verbatims contextualisés — plutôt qu'un slogan qui simplifie le conflit ou caricature les personnes."
  },
  {
    keywords: ["projet de loi", "proposition de loi", "conseil constitutionnel", "reglement europeen", "decret", "interdiction", "reglementation", "directive", "loi adoptee", "nouvelle loi"],
    strategy: "Vérifier le statut juridique, la date d'entrée en vigueur et les personnes concernées ; distinguer ce qui est proposé, voté, promulgué ou déjà applicable.",
    creative: "Produire un décryptage pratique : calendrier, arbre de décision ou fiche « ce qui change / ne change pas », avec des termes simples et un lien vers le texte de référence."
  },
  {
    keywords: ["guerre", "frappes", "offensive", "armee", "militaire", "otan", "missile", "cessez-le-feu", "conflit arme", "bombardement", "otage"],
    strategy: "Vérifier l'origine, la date et le niveau de confirmation des informations ; anticiper les risques de désinformation, de polarisation et d'atteinte aux personnes.",
    creative: "Privilégier cartes sourcées, repères chronologiques et légendes précises ; écarter les images non authentifiées ou choquantes et ne pas esthétiser la violence."
  },
  {
    keywords: ["diplomatie", "sommet", "ambassadeur", "ministre des affaires etrangeres", "negociation", "accord international", "sanctions", "etats-unis", "chine", "bresil", "iran", "ukraine", "gaza", "onu", "union europeenne"],
    strategy: "Analyser les intérêts des parties et les publics selon les zones ; contextualiser les déclarations et éviter de projeter automatiquement une lecture nationale sur un événement international.",
    creative: "Adapter exemples, symboles, visuels et vocabulaire aux contextes locaux ; utiliser une carte ou une chronologie clairement sourcée plutôt qu'une représentation simplificatrice des pays concernés."
  },
  {
    keywords: ["inflation", "pouvoir d'achat", "prix en hausse", "hausse des prix", "cout de la vie", "consommation", "panier moyen", "prix alimentaires", "prix a la consommation"],
    strategy: "Évaluer la sensibilité au prix et les arbitrages des publics ; vérifier les comparaisons temporelles et relier chaque argument de valeur à un bénéfice réel et démontrable.",
    creative: "Préférer une comparaison transparente, une décomposition de prix ou un cas d'usage concret ; éviter le ton léger, les injonctions à consommer et les promesses de pouvoir d'achat non étayées."
  },
  {
    keywords: ["carburant", "petrole", "gaz", "electricite", "prix de l'energie", "energie", "detroit d'ormuz", "facture energetique"],
    strategy: "Séparer les causes immédiates des facteurs structurels et expliciter les effets possibles pour ménages, entreprises et territoires sans surattribuer une évolution à une seule cause.",
    creative: "Visualiser les mécanismes avec un schéma de chaîne d'impact ou plusieurs scénarios ; dater les chiffres, afficher les unités et rendre visibles les incertitudes."
  },
  {
    keywords: ["licenciement", "licenciements", "plan social", "suppression de postes", "emploi", "chomage", "recrutement", "salaries", "conditions de travail", "fermeture d'usine"],
    strategy: "Prioriser les salariés et les personnes directement concernées ; aligner calendrier des annonces, informations managériales et engagements d'accompagnement avant la communication externe.",
    creative: "Préparer des supports utiles plutôt que promotionnels : FAQ, calendrier, points de contact et messages personnalisés par public ; préserver la dignité des personnes et éviter les éléments de langage déshumanisants."
  },
  {
    keywords: ["resultat trimestriel", "chiffre d'affaires", "fusion", "rachat", "investissement", "faillite", "start-up", "startup", "entreprise", "entreprises", "actionnaire", "benefice net"],
    strategy: "Relier chiffres et décisions aux attentes distinctes des clients, salariés, investisseurs et partenaires ; distinguer performance ponctuelle, tendance et objectif futur.",
    creative: "Construire une narration factuelle autour de trois preuves clés — données, décision, conséquence — et choisir graphiques ou cas d'usage adaptés sans transformer une annonce en promesse excessive."
  },
  {
    keywords: ["sante", "hopital", "vaccin", "vaccination", "epidemie", "medecin", "patients", "medicament", "maladie", "soins", "sante publique", "diagnostic"],
    strategy: "Identifier les publics exposés et le niveau de preuve disponible ; faire valider les informations par une source compétente et distinguer recommandation, hypothèse et résultat confirmé.",
    creative: "Créer un contenu accessible avec définitions, étapes et consignes concrètes ; attribuer les chiffres, rendre les limites visibles et éviter les images anxiogènes ou les promesses thérapeutiques."
  },
  {
    keywords: ["ecole", "lycee", "lyceens", "universite", "etudiants", "enseignement", "education", "formation", "enseignants", "etablissement scolaire", "frais d'inscription"],
    strategy: "Segmenter étudiants, familles, équipes éducatives et décideurs ; répondre aux questions pratiques de chaque public et distinguer décision actée, expérimentation et hypothèse.",
    creative: "Décliner un même fond en FAQ, calendrier ou témoignage contextualisé ; choisir un ton accessible sans infantiliser les jeunes ni réduire les expériences à un cas isolé."
  },
  {
    keywords: ["justice", "tribunal", "proces", "condamne", "condamnation", "enquete", "police", "interpellation", "accusation", "magistrat", "parquet"],
    strategy: "Distinguer faits établis, accusations et déclarations ; vérifier la terminologie juridique et la présomption d'innocence avant toute prise de parole au nom d'une organisation.",
    creative: "S'en tenir à une chronologie et à des formulations neutres ; éviter titres insinuants, images stigmatisantes et montages qui donnent comme acquise une version encore contestée."
  },
  {
    keywords: ["climat", "rechauffement", "inondation", "secheresse", "canicule", "incendie", "tempete", "biodiversite", "pollution", "emissions", "catastrophe naturelle"],
    strategy: "Relier l'enjeu à ses effets territoriaux et aux responsabilités des acteurs ; vérifier périmètre, période et méthode des chiffres pour limiter le risque de greenwashing ou de dramatisation.",
    creative: "Montrer les preuves et les changements observables avec données contextualisées, cartes ou visuels de terrain ; privilégier des résultats mesurables aux images génériques de nature."
  },
  {
    keywords: ["transition energetique", "energies renouvelables", "eolien", "solaire", "nucleaire", "voiture electrique", "batterie", "decarbonation"],
    strategy: "Mettre en regard bénéfices, coûts, usages et limites environnementales ; préciser l'horizon temporel et ne pas présenter un arbitrage technologique comme une solution sans contrepartie.",
    creative: "Expliquer le fonctionnement par schéma ou comparaison de scénarios ; rendre visibles les ordres de grandeur, les limites et les étapes de déploiement, sans esthétiser une promesse abstraite."
  },
  {
    keywords: ["cinema", "film", "serie", "acteur", "actrice", "realisateur", "festival", "streaming", "plateforme de streaming", "sortie en salles"],
    strategy: "Analyser le parcours d'attention entre annonce, bande-annonce, critique, sortie et bouche-à-oreille ; identifier communautés, relais de prescription et calendrier de diffusion.",
    creative: "Faire émerger une signature visuelle et une accroche propres à l'œuvre ; décliner teaser, extrait et contenu en coulisses sans révéler l'intrigue ni promettre une expérience que l'œuvre ne tient pas."
  },
  {
    keywords: ["livre", "roman", "ecrivain", "ecrivaine", "litterature", "goncourt", "prix litteraire", "edition", "librairie", "auteur"],
    strategy: "Étudier comment critiques, prix, libraires et communautés contribuent à la prescription ; distinguer visibilité médiatique, ventes et réception critique.",
    creative: "Créer une porte d'entrée dans l'univers du livre — extrait autorisé, portrait d'auteur ou recommandation contextualisée — en respectant les droits et sans réduire l'œuvre à son classement commercial."
  },
  {
    keywords: ["musique", "chanteur", "chanteuse", "album", "concert", "tournee", "festival de musique", "artiste musical"],
    strategy: "Relier sortie, scène, plateformes et communauté de fans ; cartographier les relais crédibles et distinguer engagement communautaire, écoutes et ventes.",
    creative: "Développer un univers visuel et sonore cohérent entre teaser, extrait et contenu en direct ; donner aux fans une matière partageable sans négliger droits musicaux et autorisations d'image."
  },
  {
    keywords: ["sport", "football", "rugby", "tennis", "basket", "formule 1", "grand prix", "championnat", "olympique", "coupe du monde", "match", "athlete", "club sportif"],
    strategy: "Cartographier les parties prenantes — supporters, athlètes, clubs, sponsors et organisateurs — et anticiper les effets d'une performance ou polémique sur la réputation.",
    creative: "Transformer le temps fort en récit documenté : séquence clé, données de performance ou portrait ; cadrer les images et les prises de parole sans instrumentaliser les athlètes ni les supporters."
  },
  {
    keywords: ["decouverte scientifique", "chercheurs", "chercheur", "recherche", "etude scientifique", "publication scientifique", "nobel", "astronomie", "espace", "nasa", "neurone", "mathematiques", "essai clinique"],
    strategy: "Distinguer résultat observé, hypothèse et application possible ; contrôler la source originale, la taille de l'étude et les limites avant de transformer une découverte en promesse.",
    creative: "Expliquer un mécanisme complexe par analogie vérifiable, schéma ou étapes ; faire apparaître la source et les incertitudes au même niveau visuel que le résultat annoncé."
  },
  {
    keywords: ["media", "medias", "journaliste", "journalisme", "television", "radio", "presse", "chaine d'information", "redaction", "desinformation", "fake news", "journal"],
    strategy: "Distinguer information journalistique, communication institutionnelle, publicité et opinion ; vérifier l'origine des chiffres, images et citations avant reprise ou commentaire.",
    creative: "Rendre la provenance visible par des citations attribuées, une chronologie ou un comparatif de sources ; préférer l'explication vérifiable au titre sensationnaliste qui amplifie la désinformation."
  }
];

const CATEGORY_CREATIVE_FALLBACKS = {
  "politique": "Construire un décryptage neutre — chronologie, acteurs, effets concrets — avec chiffres sourcés et hiérarchie visuelle qui sépare faits et commentaires.",
  "economie": "Utiliser une infographie, une comparaison ou un cas d'usage pour rendre les effets compréhensibles ; dater les données et expliquer les unités sans dramatiser les résultats.",
  "societe": "Faire émerger les expériences des publics concernés avec un vocabulaire précis, des exemples contextualisés et une représentation qui évite stéréotypes et généralisation.",
  "international": "Apporter les repères indispensables — carte, chronologie, traduction des termes — et adapter références et visuels aux contextes culturels concernés.",
  "sciences & tech": "Décomposer le sujet en étapes ou cas d'usage, citer la source et rendre les limites lisibles au lieu de promettre une technologie miraculeuse.",
  "culture": "Créer un angle éditorial qui relie l'œuvre ou l'événement à son contexte ; varier extrait, coulisses et recommandation en respectant droits et communautés.",
  "sport": "Articuler émotion, donnée et récit de terrain dans des formats complémentaires, en vérifiant les statistiques et les droits à l'image.",
  "medias & communication": "Montrer le fonctionnement du canal ou du récit avec un exemple concret, une comparaison sourcée ou une démonstration, plutôt qu'une formule abstraite.",
  "environnement": "Rendre visibles les preuves et les conséquences concrètes par des données datées, une carte ou des images de terrain ; éviter les promesses écologiques sans mesure.",
};

const CATEGORY_STRATEGY_FALLBACKS = {
  "politique": "Distinguer annonce, arbitrage et mesure effective ; hiérarchiser les publics concernés et anticiper les questions concrètes que soulève la décision.",
  "economie": "Relier l'indicateur économique à ses effets sur les publics et les décisions ; distinguer tendance, résultat ponctuel et projection.",
  "societe": "Identifier les groupes directement concernés, leurs expériences divergentes et les risques de représentation simplificatrice avant de choisir l'angle.",
  "international": "Contextualiser les faits selon les pays et les parties prenantes ; vérifier l'origine des informations et les sensibilités locales.",
  "sciences & tech": "Vérifier ce qui est démontré, testé ou seulement envisagé ; expliciter les usages, les limites et les incertitudes.",
  "culture": "Identifier les communautés, prescripteurs et contextes qui donnent du sens au sujet ; ne pas confondre attention médiatique et réception réelle.",
  "sport": "Analyser l'effet sur l'image des personnes, clubs, organisateurs et partenaires ; distinguer émotion immédiate et impact réputationnel durable.",
  "medias & communication": "Examiner la confiance dans le canal, les responsabilités éditoriales et la façon dont le message est distribué, compris et commenté.",
  "environnement": "Relier les engagements aux effets mesurables, au périmètre de preuve et aux publics touchés pour prévenir les promesses disproportionnées.",
};

function normalizeForAnalysis(value) {
  return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("fr");
}

function communicationAnalysisFor(item) {
  const subject = normalizeForAnalysis(`${item.title || ""} ${item.summary || ""}`);
  const matchedRule = COMMUNICATION_ANALYSIS_RULES.find(rule =>
    rule.keywords.some(keyword => subject.includes(keyword))
  );
  if (matchedRule) return { strategy: matchedRule.strategy, creative: matchedRule.creative };

  const category = normalizeForAnalysis(item.category || "");
  const storedAngle = Array.isArray(item.communication_angle)
    ? item.communication_angle.filter(part => typeof part === "string").join(" ").trim()
    : safeText(item.communication_angle);
  return {
    strategy: storedAngle || CATEGORY_STRATEGY_FALLBACKS[category] || "Identifier les publics concernés, les conséquences concrètes du sujet et les preuves nécessaires avant toute prise de parole.",
    creative: CATEGORY_CREATIVE_FALLBACKS[category] || "Choisir un format qui explique le sujet sans le simplifier à l'excès ; rendre sources, exemples et informations clés immédiatement repérables."
  };
}

function createCommunicationPointList(item) {
  const list = document.createElement("ul");
  list.className = "angle-copy angle-points";
  const analysis = communicationAnalysisFor(item);
  [
    { label: "Stratégie", text: analysis.strategy },
    { label: "Création", text: analysis.creative }
  ].forEach(point => {
    const entry = document.createElement("li");
    const label = document.createElement("strong");
    label.textContent = `${point.label} — `;
    entry.append(label, document.createTextNode(point.text));
    list.append(entry);
  });
  return list;
}
function renderFeatured(data) {
  if (!featuredGrid) return;
  const stories = Array.isArray(data.featured_news) ? data.featured_news.slice(0, 20) : [];
  featuredGrid.replaceChildren();
  if (featuredStart) featuredStart.textContent = formatShortDate(data.featured_window_start);
  if (featuredEnd) featuredEnd.textContent = formatShortDate(data.featured_window_end || data.last_updated);
  if (featuredMeta) {
    const pool = Number(data.featured_pool_count || 0);
    const sources = Number(data.featured_sources_count || 0);
    featuredMeta.textContent = stories.length
      ? `${stories.length} sujets retenus parmi ${pool} articles récents · ${sources} sources suivies`
      : "En attente des articles de la dernière semaine";
  }
  if (featuredEmpty) featuredEmpty.hidden = stories.length > 0;
  stories.forEach((story, index) => {
    const card = document.createElement("article");
    card.className = "top-story-card";
    const top = document.createElement("div");
    top.className = "top-story-card-top";
    const rank = document.createElement("span");
    rank.className = "top-story-rank";
    rank.textContent = String(index + 1).padStart(2, "0");
    const category = document.createElement("span");
    category.className = "top-story-category";
    category.textContent = safeText(story.category, "Actualité");
    category.dataset.category = safeText(story.category, "Actualité");
    top.append(rank, category);
    const title = document.createElement("h3");
    title.className = "top-story-title";
    title.textContent = safeText(story.title, "Actualité");
    const summary = document.createElement("p");
    summary.className = "top-story-summary";
    summary.textContent = safeText(story.summary, "Consultez la source originale pour les détails.");
    const coverage = document.createElement("p");
    coverage.className = "top-story-coverage";
    const sourceCount = Number(story.coverage_count || (story.coverage_sources || []).length || 1);
    const mentionCount = Number(story.mention_count || 1);
    coverage.textContent = `${sourceCount} média${sourceCount > 1 ? "s" : ""} · ${mentionCount} article${mentionCount > 1 ? "s" : ""} lié${mentionCount > 1 ? "s" : ""}`;
    const sourceLine = document.createElement("p");
    sourceLine.className = "top-story-sources";
    const names = Array.isArray(story.coverage_sources) ? story.coverage_sources : [];
    sourceLine.textContent = names.slice(0, 3).join(" · ") + (names.length > 3 ? ` · +${names.length - 3}` : "");
    const angle = document.createElement("div");
    angle.className = "communication-angle top-story-communication-angle";
    const angleIcon = document.createElement("span");
    angleIcon.className = "angle-icon";
    angleIcon.textContent = "✳";
    const angleContent = document.createElement("div");
    const angleHeading = document.createElement("strong");
    angleHeading.textContent = "Pourquoi c’est important en communication";
    const angleCopy = createCommunicationPointList(story);
    angleContent.append(angleHeading, angleCopy);
    angle.append(angleIcon, angleContent);
    const footer = document.createElement("div");
    footer.className = "top-story-footer";
    const date = document.createElement("time");
    date.textContent = formatDate(story.published_at);
    const link = document.createElement("a");
    link.className = "top-story-link";
    link.textContent = "Lire ↗";
    if (story.url && /^https?:\/\//i.test(story.url)) {
      link.href = story.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.setAttribute("aria-label", `Lire l’article source : ${safeText(story.title, "actualité")}`);
    } else {
      link.removeAttribute("href");
      link.textContent = "Source indisponible";
    }
    footer.append(date, link);
    card.append(top, title, summary, coverage, sourceLine, angle, footer);
    featuredGrid.append(card);
  });
}

function render() {
  const query = searchInput.value.trim().toLocaleLowerCase("fr");
  let filtered = allNews.filter(item => {
    const matchesCategory = selectedCategory === "Toutes" || item.category === selectedCategory;
    const searchable = [item.title, item.summary, item.source, item.category, item.communication_angle].join(" ").toLocaleLowerCase("fr");
    return matchesCategory && searchable.includes(query);
  });
  if (sortSelect.value === "source") filtered.sort((a,b) => safeText(a.source).localeCompare(safeText(b.source), "fr"));
  else filtered.sort((a,b) => new Date(b.published_at || 0) - new Date(a.published_at || 0));
  grid.replaceChildren();
  filtered.slice(0, visibleCount).forEach(item => {
    const fragment = template.content.cloneNode(true);
    const categoryTag = fragment.querySelector(".category-tag");
    categoryTag.textContent = safeText(item.category, "Actualité");
    categoryTag.dataset.category = safeText(item.category, "Actualité");
    fragment.querySelector("time").textContent = formatDate(item.published_at);
    fragment.querySelector(".news-title").textContent = safeText(item.title, "Actualité");
    fragment.querySelector(".news-summary").textContent = safeText(item.summary, "Ouvrez l’article source pour consulter les détails.");
    fragment.querySelector(".angle-copy").replaceWith(createCommunicationPointList(item));
    fragment.querySelector(".source-name").textContent = safeText(item.source, "Média source");
    const link = fragment.querySelector(".read-link");
    if (item.url && /^https?:\/\//i.test(item.url)) link.href = item.url;
    else { link.removeAttribute("href"); link.textContent = "Source indisponible"; }
    grid.append(fragment);
  });
  resultCount.textContent = `${filtered.length} article${filtered.length > 1 ? "s" : ""} dans la sélection`;
  emptyState.hidden = filtered.length !== 0;
  loadMore.hidden = filtered.length <= visibleCount;
}
function setCategory(category) {
  selectedCategory = category;
  visibleCount = PAGE_SIZE;
  document.querySelectorAll(".category-chip").forEach(button => {
    const active = button.dataset.category === category;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  render();
}
function setRefreshState(loading) {
  if (!refreshButton) return;
  refreshButton.disabled = loading;
  refreshButton.classList.toggle("is-loading", loading);
  refreshButton.setAttribute("aria-busy", String(loading));
  refreshButton.querySelector(".refresh-label").textContent = loading ? "Actualisation…" : "Actualiser";
}
async function loadNews({ manual = false } = {}) {
  lastLoadAttemptAt = Date.now();
  const hadData = allNews.length > 0;
  if (manual) setRefreshState(true);
  try {
    // Le paramètre unique et cache:no-store forcent une relecture de news.json.
    // Le bouton actualise les données déjà publiées sur GitHub Pages ; il ne déclenche pas le workflow GitHub.
    const response = await fetch(`${DATA_URL}?refresh=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error("Le fichier de veille n’est pas disponible.");
    const data = await response.json();
    const collectedArticles = Array.isArray(data.articles) ? data.articles : [];
    allNews = keepArticlesFromLast30Days(collectedArticles);
    updateCategoryCounts();
    renderFeatured(data);
    updateLabel.textContent = formatUpdated(data.last_updated);
    statusMessage.textContent = safeText(data.note);
    statusMessage.hidden = !data.note;
    if (data.last_updated) {
      const hoursOld = (Date.now() - new Date(data.last_updated).getTime()) / 36e5;
      if (hoursOld > 2) {
        statusMessage.textContent = "La dernière collecte date de plus de deux heures. Le bouton Actualiser recharge les données publiées, mais seule la collecte GitHub Actions récupère de nouveaux articles.";
        statusMessage.hidden = false;
      }
    }
    render();
    if (manual && !data.note && data.last_updated) {
      // Confirmation discrète sans confondre rechargement du site et nouvelle collecte RSS.
      statusMessage.textContent = "Données publiées rechargées. La date ci-dessus indique quand GitHub a effectué la dernière collecte RSS.";
      statusMessage.hidden = false;
      window.setTimeout(() => { if (statusMessage.textContent.startsWith("Données publiées rechargées.")) statusMessage.hidden = true; }, 4500);
    }
  } catch (error) {
    updateLabel.textContent = hadData ? updateLabel.textContent : "Collecte en attente";
    statusMessage.textContent = hadData
      ? "Impossible de recharger les données. Les articles déjà affichés sont conservés ; réessaie dans un instant."
      : "Les articles ne sont pas encore disponibles. Vérifie que la première collecte a été lancée dans GitHub → Actions → « Actualiser ActuSUP » et que GitHub Pages est activé.";
    statusMessage.hidden = false;
    renderFeatured({ featured_news: [], featured_window_start: null, featured_window_end: null });
    render();
  } finally {
    if (manual) setRefreshState(false);
  }
}
if (featuredToggle && featuredDetails) {
  featuredToggle.addEventListener("click", () => {
    const expanded = featuredToggle.getAttribute("aria-expanded") !== "true";
    featuredToggle.setAttribute("aria-expanded", String(expanded));
    featuredDetails.hidden = !expanded;
    featuredToggle.textContent = expanded ? "Masquer les 20 actus de la semaine" : "Voir les 20 actus de la semaine";
  });
}
document.querySelectorAll(".category-chip").forEach(button => button.addEventListener("click", () => setCategory(button.dataset.category)));
searchInput.addEventListener("input", () => { visibleCount = PAGE_SIZE; render(); });
sortSelect.addEventListener("change", render);
loadMore.addEventListener("click", () => { visibleCount += PAGE_SIZE; render(); });
document.querySelector("#reset-filters").addEventListener("click", () => {
  searchInput.value = "";
  sortSelect.value = "recent";
  setCategory("Toutes");
});
if (refreshButton) refreshButton.addEventListener("click", () => loadNews({ manual: true }));

// Relit automatiquement le fichier publié toutes les dix minutes. La collecte RSS
// est lancée séparément par le workflow GitHub Actions planifié.
window.setInterval(() => {
  if (!document.hidden) loadNews();
}, AUTO_REFRESH_INTERVAL);

// Si le navigateur a suspendu l’onglet en arrière-plan, recharge à son retour
// lorsque dix minutes se sont écoulées depuis la dernière tentative.
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && Date.now() - lastLoadAttemptAt >= AUTO_REFRESH_INTERVAL) {
    loadNews();
  }
});

updateCategoryCounts();
document.addEventListener("keydown", event => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    event.preventDefault(); searchInput.focus();
  }
});
loadNews();
