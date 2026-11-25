"""Vérifie que ranking.js (repli navigateur) reste aligné sur story_ranking.py (collecteur).

Nécessite Node.js ; le test est ignoré s'il est absent. Lancer : python3 -m unittest discover -s tests -v
"""
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import story_ranking as R  # noqa: E402


@unittest.skipUnless(shutil.which("node"), "Node.js absent")
class Parity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        news = ROOT / "data" / "news.json"
        if not news.exists():
            raise unittest.SkipTest("data/news.json absent")
        data = json.loads(news.read_text(encoding="utf-8"))
        cls.now = R.parse_dt(data["last_updated"])
        cls.articles = data["articles"]
        result = subprocess.run(["node", str(ROOT / "tests" / "parity_runner.js"), str(news), cls.now.isoformat()],
                                capture_output=True, text=True, check=True, timeout=120)
        cls.js = json.loads(result.stdout)

    def test_constants_are_aligned(self):
        c = self.js["constants"]
        self.assertEqual(c["WINDOW_DAYS"], R.WINDOW_DAYS)
        self.assertEqual(c["FEATURED_LIMIT"], R.FEATURED_LIMIT)
        self.assertEqual(c["MAX_GAP_DAYS"], R.MAX_GAP_DAYS)
        self.assertEqual(c["JOIN_GROWTH"], R.JOIN_GROWTH)
        self.assertEqual(c["JOIN_THRESHOLD"], R.JOIN_THRESHOLD)
        self.assertEqual(c["MIN_SHARED_TERMS"], R.MIN_SHARED_TERMS)
        self.assertEqual(c["ENTITY_BOOST"], R.ENTITY_BOOST)
        self.assertEqual(c["TITLE_WEIGHT"], R.TITLE_WEIGHT)
        self.assertEqual(c["SUMMARY_CHARS"], R.SUMMARY_CHARS)
        self.assertEqual(c["CENTROID_TERMS"], R.CENTROID_TERMS)
        self.assertEqual(c["CORE_TERMS"], R.CORE_TERMS)

    def test_vocabularies_are_aligned(self):
        self.assertEqual(set(self.js["stopwords"]), R.STOPWORDS)
        self.assertEqual(self.js["source_priority"], R.SOURCE_PRIORITY)
        self.assertEqual(self.js["outlet_family"], R.OUTLET_FAMILY)
        self.assertEqual(self.js["hard"], R.HARD_NEWS_TERMS)
        self.assertEqual(self.js["low"], R.LOW_SIGNAL_TERMS)

    def test_text_processing_is_identical(self):
        for js, article in zip(self.js["sample"], self.articles):
            text = article["title"] + " " + (article.get("summary") or "")[:R.SUMMARY_CHARS]
            self.assertEqual(js["tokens"], R.tokenize(text), article["title"])
            self.assertEqual(js["entities"], sorted(R.entity_terms(article["title"])), article["title"])
            self.assertEqual(js["headline"], R.clean_headline(article["title"]), article["title"])

    def test_same_top_20_on_published_articles(self):
        py_stories = R.update_stories([], self.articles, self.now)
        py_top = R.build_monthly_top(py_stories, self.now)
        self.assertEqual(self.js["stories"], len(py_stories))
        self.assertEqual([t["id"] for t in self.js["top"]], [t["id"] for t in py_top])
        for js_item, py_item in zip(self.js["top"], py_top):
            self.assertAlmostEqual(js_item["importance_score"], py_item["importance_score"], places=2)
            self.assertEqual(js_item["category"], py_item["category"])
            self.assertEqual(js_item["coverage_count"], py_item["coverage_count"])
            self.assertEqual(js_item["mention_count"], py_item["mention_count"])
            self.assertEqual(js_item["active_days"], py_item["active_days"])
            self.assertEqual(js_item["title"], py_item["title"])
            self.assertEqual(js_item["coverage_sources"], py_item["coverage_sources"])


if __name__ == "__main__":
    unittest.main()
