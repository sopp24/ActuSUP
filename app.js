const DATA_URL = "data/news.json";
const PAGE_SIZE = 12;
let allNews = [];
let selectedCategory = "Toutes";
let visibleCount = PAGE_SIZE;

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
    card.append(top, title, summary, coverage, sourceLine, footer);
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
    fragment.querySelector(".category-tag").textContent = safeText(item.category, "Actualité");
    fragment.querySelector("time").textContent = formatDate(item.published_at);
    fragment.querySelector(".news-title").textContent = safeText(item.title, "Actualité");
    fragment.querySelector(".news-summary").textContent = safeText(item.summary, "Ouvrez l’article source pour consulter les détails.");
    fragment.querySelector(".angle-copy").textContent = safeText(item.communication_angle, `Pour comprendre les implications de « ${safeText(item.title, "cette actualité")} », un communicant doit identifier les publics concernés, les risques de perception et les messages à adapter au contexte.`);
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
  const hadData = allNews.length > 0;
  if (manual) setRefreshState(true);
  try {
    // Le paramètre unique et cache:no-store forcent une relecture de news.json.
    // Le bouton actualise les données déjà publiées sur GitHub Pages ; il ne déclenche pas le workflow GitHub.
    const response = await fetch(`${DATA_URL}?refresh=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) throw new Error("Le fichier de veille n’est pas disponible.");
    const data = await response.json();
    allNews = Array.isArray(data.articles) ? data.articles : [];
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
document.addEventListener("keydown", event => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
    event.preventDefault(); searchInput.focus();
  }
});
loadNews();
