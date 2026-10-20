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
