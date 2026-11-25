"""Tests du regroupement par histoire et du classement des actualités du mois (stdlib uniquement).

Lancer : python3 -m unittest discover -s tests -v
"""
import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import story_ranking as R  # noqa: E402

NOW = datetime(2026, 11, 25, 9, 0, tzinfo=timezone.utc)
_counter = [0]


def art(title, source, hours_ago=1.0, summary="", category="Société", feed_rank=10, days_ago=0.0):
    _counter[0] += 1
    published = NOW - timedelta(hours=hours_ago, days=days_ago)
    return {
        "id": f"id{_counter[0]:06d}",
        "title": title,
        "summary": summary or f"Résumé de l’article numéro {_counter[0]}.",
        "source": source,
        "url": f"https://exemple.test/{_counter[0]}",
        "published_at": published.isoformat(),
        "category": category,
        "feed_rank": feed_rank,
    }


OUTLETS = ["Le Monde", "Le Figaro", "Libération", "France 24", "RFI", "BFMTV", "Les Échos", "20 Minutes",
           "Ouest-France", "Franceinfo (TV)", "L'Obs", "Le Point"]


def story_wave(title_variants, outlets, **kwargs):
    return [art(title_variants[i % len(title_variants)], outlet, **kwargs) for i, outlet in enumerate(outlets)]


class TextHelpers(unittest.TestCase):
    def test_tokenize_folds_accents_plural_and_stopwords(self):
        self.assertEqual(R.tokenize("Les Élections législatives : des députés manifestent"),
                         ["election", "legislative", "depute", "manifestent"])
        self.assertEqual(R.tokenize("Le 12 mars, 3 jours de grève"), ["greve"])  # nombres et mots vides écartés

    def test_entities_are_capitalised_words_except_first(self):
        self.assertEqual(R.entity_terms("Incendie à Marseille : le préfet Hugues Moutouh réagit"),
                         {"marseille", "hugue", "moutouh"})
        self.assertIn("rn", R.entity_terms("Le préfet est soupçonné d’être une taupe du RN"))
        self.assertEqual(R.entity_terms("une phrase sans nom propre"), set())

    def test_clean_headline_removes_live_prefixes_but_not_real_titles(self):
        self.assertEqual(R.clean_headline("EN DIRECT, guerre en Ukraine : Kiev a frappé deux navires"),
                         "Guerre en Ukraine : Kiev a frappé deux navires")
        self.assertEqual(R.clean_headline("☕️ Un système de la CIA victime d’une intrusion"),
                         "Un système de la CIA victime d’une intrusion")
        self.assertEqual(R.clean_headline("Direct : oui"), "Direct : oui")  # reste trop court pour être « nettoyé »
        self.assertEqual(R.clean_headline("Le directeur annonce son départ"), "Le directeur annonce son départ")

    def test_paris_day_uses_local_calendar(self):
        late = datetime(2026, 11, 24, 23, 30, tzinfo=timezone.utc)  # 00:30 à Paris le 25
        self.assertEqual(R.paris_day(late), "2026-11-25")

    def test_outlet_family_counts_once(self):
        self.assertEqual(R.outlet_key("France Info (Radio)"), R.outlet_key("Franceinfo (TV)"))
        self.assertEqual(R.outlet_key("RMC"), R.outlet_key("BFMTV"))
        self.assertGreater(R.outlet_weight("Le Monde"), R.outlet_weight("CB News"))
        self.assertEqual(R.outlet_weight("Média inconnu"), 0.6)


class Clustering(unittest.TestCase):
    def test_same_story_from_several_outlets_is_one_story(self):
        titles = [
            "Incendie à Marseille : trois blessés, le préfet des Bouches-du-Rhône réagit",
            "Marseille : un violent incendie fait trois blessés dans un immeuble",
            "Après l’incendie de Marseille, le préfet annonce une enquête sur l’immeuble",
        ]
        stories = R.update_stories([], story_wave(titles, OUTLETS[:5]), NOW)
        self.assertEqual(len(stories), 1)
        self.assertEqual(len(stories[0]["o"]), 5)

    def test_unrelated_stories_stay_separate(self):
        articles = (
            story_wave(["Incendie à Marseille : trois blessés dans un immeuble"], OUTLETS[:3])
            + story_wave(["Sommet sur le climat à Belém : les États peinent à s’accorder"], OUTLETS[3:6])
            + story_wave(["Le XV de France bat l’Argentine au Stade de France"], OUTLETS[6:9])
        )
        stories = R.update_stories([], articles, NOW)
        self.assertEqual(sorted(len(s["o"]) for s in stories), [3, 3, 3])

    def test_same_entity_different_events_are_not_chained(self):
        # Même personnalité, deux événements distincts : ne doivent pas fusionner par simple nom propre.
        a = story_wave(["Emmanuel Macron inaugure une usine de batteries à Dunkerque"], OUTLETS[:3], days_ago=0)
        b = story_wave(["Emmanuel Macron reçoit le chancelier allemand pour un dîner de travail"], OUTLETS[3:6], days_ago=0)
        stories = R.update_stories([], a + b, NOW)
        self.assertEqual(len(stories), 2)

    def test_story_expires_after_gap_and_restarts(self):
        old = story_wave(["Grève des contrôleurs aériens : de nombreux vols annulés"], OUTLETS[:3], days_ago=12)
        new = story_wave(["Grève des contrôleurs aériens : de nombreux vols annulés"], OUTLETS[3:6], days_ago=0)
        self.assertEqual(len(R.update_stories([], old + new, NOW)), 2)

    def test_story_continues_over_several_days(self):
        wave = []
        for day in range(5):
            wave += story_wave(["Inondations dans le Pas-de-Calais : des communes évacuées"], OUTLETS[day:day + 3], days_ago=day)
        stories = R.update_stories([], wave, NOW)
        self.assertEqual(len(stories), 1)
        self.assertEqual(len(stories[0]["d"]), 5)

    def test_articles_outside_window_or_undated_are_ignored(self):
        too_old = art("Un très vieux sujet sur le budget", "Le Monde", days_ago=45)
        future = art("Un sujet daté du futur lointain", "Le Monde", days_ago=-5)
        undated = dict(art("Un sujet sans date de publication", "Le Monde"), published_at=None)
        self.assertEqual(R.update_stories([], [too_old, future, undated], NOW), [])

    def test_update_is_incremental_and_idempotent(self):
        first = story_wave(["Procès Zecler : les policiers condamnés à de la prison ferme"], OUTLETS[:3])
        archive = R.update_archive({}, first, NOW)
        again = R.update_archive(archive, first, NOW + timedelta(minutes=30))  # mêmes articles revus
        self.assertEqual(again["stories"][0]["m"], 3)
        later = story_wave(["Procès Zecler : les policiers condamnés à de la prison ferme"], OUTLETS[3:5], hours_ago=0.2)
        merged = R.update_archive(again, first + later, NOW + timedelta(minutes=45))
        self.assertEqual(len(merged["stories"]), 1)
        self.assertEqual((merged["stories"][0]["m"], len(merged["stories"][0]["o"])), (5, 5))

    def test_same_id_in_two_feeds_counts_once_but_keeps_both_outlets(self):
        one = art("Panne mondiale chez Microsoft : le service est rétabli", "Le Monde")
        two = dict(one, source="Le Figaro")  # même id : même titre et même URL
        stories = R.update_stories([], [one, two], NOW)
        self.assertEqual((stories[0]["m"], len(stories[0]["o"])), (1, 2))

    def test_deduplicated_article_keeps_coverage_sources(self):
        rep = dict(art("Accord historique sur le climat à la COP31", "Le Monde"),
                   coverage_sources=["Le Monde", "RFI", "France 24"], mention_count=3)
        stories = R.update_stories([], [rep], NOW)
        self.assertEqual((stories[0]["m"], sorted(stories[0]["o"])), (3, ["France 24", "Le Monde", "RFI"]))

    def test_archive_ignores_old_articles_already_processed(self):
        first = story_wave(["Séisme en Turquie : de nombreux immeubles effondrés"], OUTLETS[:3], hours_ago=30)
        archive = R.update_archive({}, first, NOW - timedelta(hours=29))
        # Les mêmes articles sont publiés avant « since » : ignorés sans avoir besoin d'être mémorisés.
        again = R.update_archive(archive, first, NOW)
        self.assertEqual(again["stories"][0]["m"], 3)


class Scoring(unittest.TestCase):
    def rank(self, articles, **kwargs):
        stories = R.update_stories([], articles, NOW)
        return R.build_monthly_top(stories, NOW, **kwargs)

    def test_breadth_beats_repetition_by_one_outlet(self):
        repeated = [art(f"Rumeur sur le transfert de la star du PSG numéro {i}", "Le Figaro") for i in range(12)]
        broad = story_wave(["Réforme des retraites : le gouvernement présente son projet"], OUTLETS[:6])
        top = self.rank(repeated + broad)
        self.assertIn("retraites", top[0]["title"])

    def test_persistence_over_days_beats_one_day_burst(self):
        persistent = []
        for day in range(6):
            persistent += story_wave(["Crue de la Loire : vigilance rouge, des évacuations en cours"], OUTLETS[:3], days_ago=day, hours_ago=2)
        burst = story_wave(["Fusion de deux géants de l’agroalimentaire annoncée ce matin"], OUTLETS[:3], hours_ago=2)
        top = self.rank(persistent + burst)
        self.assertIn("Loire", top[0]["title"])

    def test_recency_decay_is_soft(self):
        old = story_wave(["Chute du gouvernement : motion de censure adoptée à l’Assemblée"], OUTLETS[:6], days_ago=25)
        recent = story_wave(["Trois blessés dans une collision entre deux trains près de Lyon"], OUTLETS[:3], hours_ago=2)
        top = self.rank(old + recent)
        # Un grand sujet de début de mois reste devant un fait divers récent peu relayé.
        self.assertIn("gouvernement", top[0]["title"])
        old_story = R.update_stories([], old, NOW)[0]
        self.assertGreater(R.score_story(old_story, NOW), 0.6 * R.score_story(old_story, NOW - timedelta(days=25)))

    def test_low_signal_content_is_demoted(self):
        lifestyle = story_wave(["Horoscope du jour : nos conseils et bon plan du week-end"], OUTLETS[:6])
        news = story_wave(["Attentat déjoué à Lyon : quatre suspects interpellés par la police"], OUTLETS[:4])
        top = self.rank(lifestyle + news)
        self.assertIn("Attentat", top[0]["title"])

    def test_recurring_dated_rubrics_are_demoted(self):
        rubric = story_wave(["Un jeudi soir sur la terre du jeudi 19 novembre 2026"], OUTLETS[:4])
        news = story_wave(["Grève nationale dans les raffineries : pénurie de carburant à craindre"], OUTLETS[:4])
        top = self.rank(rubric + news)
        self.assertIn("raffineries", top[0]["title"])

    def test_single_outlet_stories_are_excluded_when_enough_confirmed_ones_exist(self):
        confirmed = []
        topics = ["Séisme", "Inondation", "Grève", "Élection", "Procès", "Attentat", "Tempête", "Faillite", "Épidémie", "Accord"]
        places = ["Lima", "Hanoï", "Nairobi", "Oslo", "Quito", "Bamako", "Dakar", "Lisbonne", "Zagreb", "Tunis"]
        for i in range(22):
            confirmed += story_wave([f"{topics[i % 10]} {places[i // 2 % 10]} {['alpha','bravo'][i % 2]} {i}"], OUTLETS[:3] if i % 2 else OUTLETS[3:6])
        solos = [art(f"Billet singulier numéro {i} sur un sujet inédit {places[i % 10]}", "Konbini") for i in range(15)]
        top = self.rank(confirmed + solos)
        self.assertTrue(all(item["coverage_count"] >= 2 for item in top), [i["title"] for i in top if i["coverage_count"] < 2])

    def test_fills_with_best_remaining_when_few_confirmed_stories(self):
        top = self.rank(story_wave(["Séisme à Lima : plusieurs victimes"], OUTLETS[:3]) + [art("Un fait divers isolé à Pau", "Sud Ouest")])
        self.assertEqual(len(top), 2)

    def test_category_diversity_without_hiding_a_dominant_story(self):
        # 26 sujets sportifs de même ampleur et 4 sujets d'autres rubriques : le sport ne doit pas
        # monopoliser le haut du classement, mais la liste est quand même complétée jusqu'à 20.
        articles = []
        sports_names = ["rugby", "football", "tennis", "cyclisme", "handball", "basket", "natation", "judo", "voile", "golf"]
        for i in range(26):
            articles += story_wave([f"Finale de {sports_names[i % 10]} à Stade{i} : victoire d'Équipe{i} devant Rival{i}"], OUTLETS[:5], category="Sport")
        others = ["Réforme des retraites : manifestation massive à Paris",
                  "Budget 2027 : le gouvernement engage sa responsabilité",
                  "Procès de l’attentat de Nice : le verdict est attendu",
                  "Tempête Ciaran : des milliers de foyers privés d’électricité"]
        for i, title in enumerate(others):
            articles += story_wave([title], OUTLETS[:5], category=["Société", "Politique", "Société", "Environnement"][i])
        top = self.rank(articles)
        self.assertEqual(len(top), R.FEATURED_LIMIT)
        first_ten = top[:10]
        self.assertEqual(sum(1 for item in first_ten if item["category"] != "Sport"), 4)
        self.assertLessEqual(sum(1 for item in first_ten if item["category"] == "Sport"), R.FEATURED_LIMIT // 3)

    def test_truly_dominant_story_stays_first(self):
        big = story_wave(["Guerre en Ukraine : offensive russe massive sur Kiev"], OUTLETS)
        others = [x for i in range(6) for x in story_wave([f"Sujet moyen {i} Ville{i} événement{i}"], OUTLETS[:3])]
        self.assertIn("Ukraine", self.rank(big + others)[0]["title"])

    def test_near_duplicate_stories_do_not_fill_two_slots(self):
        a = story_wave(["Procès Zecler : trois policiers condamnés à des peines de prison"], OUTLETS[:6], days_ago=0)
        b = story_wave(["Verdict du procès Zecler : trois policiers condamnés"], OUTLETS[6:10], days_ago=6)  # après l'extinction du premier
        top = self.rank(a + b)
        self.assertEqual(len(top), 1 if len(R.update_stories([], a + b, NOW)) == 1 else len([t for t in top if "Zecler" in t["title"]]))
        self.assertLessEqual(len([t for t in top if "Zecler" in t["title"]]), 1)

    def test_featured_item_format_is_backward_compatible(self):
        top = self.rank(story_wave(["EN DIRECT, guerre en Ukraine : Kiev frappe deux navires russes en Libye"], OUTLETS[:4], feed_rank=1))
        item = top[0]
        for key in ("id", "title", "summary", "source", "url", "published_at", "category", "feed_rank",
                    "coverage_sources", "coverage_count", "mention_count", "importance_score", "latest_coverage_at"):
            self.assertIn(key, item)
        self.assertEqual(item["coverage_count"], len(item["coverage_sources"]))
        self.assertEqual(item["title"], "Guerre en Ukraine : Kiev frappe deux navires russes en Libye")
        self.assertEqual(item["active_days"], 1)
        json.dumps(top)  # sérialisable

    def test_archive_roundtrip_is_json_serialisable_and_stable(self):
        articles = story_wave(["Séisme à Lima : plusieurs victimes dans la capitale"], OUTLETS[:4])
        archive = R.update_archive({}, articles, NOW)
        restored = json.loads(json.dumps(archive))
        self.assertEqual(R.build_monthly_top(restored["stories"], NOW), R.build_monthly_top(archive["stories"], NOW))
        self.assertEqual([s["id"] for s in archive["stories"]], sorted(s["id"] for s in archive["stories"]))

    def test_prune_keeps_confirmed_and_fresh_only(self):
        confirmed = story_wave(["Faillite d’un grand groupe de BTP : 3000 emplois menacés"], OUTLETS[:3], hours_ago=30)
        stale_single = [art("Un article isolé d’il y a deux jours à Pau", "Sud Ouest", hours_ago=50)]
        fresh_single = [art("Un article isolé très récent à Rodez", "Sud Ouest", hours_ago=0.5)]
        stories = R.update_stories([], confirmed + stale_single + fresh_single, NOW)
        kept = R.prune_archive(stories, NOW)
        titles = {s["rep"]["title"] for s in kept}
        self.assertEqual(len(kept), 2)
        self.assertTrue(any("Faillite" in t for t in titles) and any("Rodez" in t for t in titles))


class RealDataSmoke(unittest.TestCase):
    """Le classement tourne sur le JSON réellement publié (si présent) sans erreur et respecte les invariants."""

    def test_top_20_on_published_data(self):
        path = Path(__file__).resolve().parent.parent / "data" / "news.json"
        if not path.exists():
            self.skipTest("data/news.json absent")
        data = json.loads(path.read_text(encoding="utf-8"))
        now = R.parse_dt(data["last_updated"])
        top = R.build_monthly_top(R.update_archive({}, data["articles"], now)["stories"], now)
        self.assertLessEqual(len(top), R.FEATURED_LIMIT)
        self.assertEqual(len({t["id"] for t in top}), len(top))
        scores = [t["importance_score"] for t in top]
        self.assertTrue(all(isinstance(s, float) for s in scores))
        for item in top:
            self.assertTrue(item["url"].startswith("http"))
            self.assertGreaterEqual(item["coverage_count"], 1)


if __name__ == "__main__":
    unittest.main()
