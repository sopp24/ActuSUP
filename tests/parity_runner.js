// Exécute ranking.js sur un JSON d'articles et affiche constantes + classement (utilisé par test_parity.py).
const fs = require("fs");
const path = require("path");
const R = require(path.join(__dirname, "..", "ranking.js"));
const input = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const now = Date.parse(process.argv[3]);
const stories = R.updateStories(input.articles, now);
const top = R.selectTopStories(stories, now).map(R.storyToFeatured);
const sample = input.articles.slice(0, 80).map(a => ({
  title: a.title, tokens: R.tokenize(a.title + " " + (a.summary || "").slice(0, 320)), entities: Array.from(R.entityTerms(a.title)).sort(),
  headline: R.cleanHeadline(a.title)
}));
process.stdout.write(JSON.stringify({
  constants: R.constants, stopwords: R.STOPWORDS.sort(), source_priority: R.SOURCE_PRIORITY, outlet_family: R.OUTLET_FAMILY,
  hard: R.HARD_NEWS_TERMS, low: R.LOW_SIGNAL_TERMS, stories: stories.length, top, sample
}));
