"""Exercise badge discovery, upgrades, caching, and failed refreshes offline."""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".github/scripts"))
import achievements
import sync_achievements as sync

PNG = (ROOT / "assets/achievements/pull-shark.png").read_bytes()
USER = "Antech-greyhat"
OVERVIEW_URL = f"https://github.com/{USER}?tab=achievements"
BASE_DATE = "2026-04-13T11:03:19Z"
BRONZE_DATE = "2026-09-16T14:05:18Z"
GOLD_DATE = "2026-11-17T14:00:00Z"
SOURCES = ["https://github.com/technorant/MarineAssistant/pull/2",
           "https://github.com/Antech-greyhat/Learn.py/pull/1",
           "https://github.com/Antech-greyhat/Emobilis-Template/pull/1",
           "https://github.com/Antech-greyhat/Example/pull/1024"]


def card(slug="pull-shark", count=1, name="Pull Shark"):
    label = f'<span class="achievement-tier-label">x{count}</span>' if count > 1 else ""
    return f'''<details data-achievement-slug="{slug}"><summary>
      <img class="achievement-badge-card" src="https://github.githubassets.com/assets/{slug}-{count}.png">
      <h3>{name}</h3>{label}</summary>
      <details-dialog src="/users/{USER}/achievements/{slug}/detail"></details-dialog></details>'''


def detail(slug="pull-shark", count=1, timestamp=BASE_DATE):
    images = ''.join(f'<img class="tier-badge" src="/{slug}-{i}.png">' for i in range(count))
    rows = ''.join(
        f'<div class="TimelineItem achievement-history-tier"><a href="{SOURCES[i]}">Activity</a>'
        f'<span>{(2, 16, 128, 1024)[i]}th pull request merged</span></div>'
        for i in range(count))
    return f'<h3>{slug}</h3>{images}<relative-time datetime="{timestamp}"></relative-time>{rows}'


def previous(count=1):
    history = [{"tier": sync.TIERS[i], "at": (BASE_DATE, BRONZE_DATE, "2026-10-29T04:30:20Z")[i],
                "date_basis": "github_unlock" if i == 0 else "milestone_activity",
                "milestone": f"{(2, 16, 128)[i]} merged pull requests", "source": SOURCES[i]}
               for i in range(count)]
    return {"username": USER, "verified_on": "2026-11-17", "badges": [{
        "slug": "pull-shark", "name": "Pull Shark", "badge_image": "assets/achievements/pull-shark.png",
        "badge_image_url": f"https://github.githubassets.com/assets/pull-shark-{count}.png", "history": history}]}


class FakeGitHub:
    def __init__(self, cards, details=None, dates=None, artwork=PNG):
        self.page = cards
        self.details = details or {}
        self.dates = dates or {}
        self.artwork = artwork
        self.requests = []
        self.date_requests = []

    def fetch(self, url, fragment=False):
        self.requests.append((url, fragment))
        if url == OVERVIEW_URL:
            return self.page.encode()
        if fragment:
            slug = url.split('/')[-2]
            return self.details[slug].encode()
        return self.artwork

    def activity_date(self, source):
        self.date_requests.append(source)
        return self.dates.get(source)


class AchievementUpdates(unittest.TestCase):
    def test_unchanged_badges_need_only_one_request(self):
        saved = previous()
        client = FakeGitHub(card())
        data, images = sync.collect(saved, client)
        self.assertEqual(data["badges"], saved["badges"])
        self.assertEqual(images, {})
        self.assertEqual(client.requests, [(OVERVIEW_URL, False)])
        self.assertEqual(client.date_requests, [])

    def test_new_badge_is_discovered_without_a_slug_allowlist(self):
        client = FakeGitHub(card() + card("new-helper", name="New Helper"),
                            {"new-helper": detail("new-helper")})
        data, images = sync.collect(previous(), client)
        self.assertEqual([badge["slug"] for badge in data["badges"]], ["pull-shark", "new-helper"])
        self.assertEqual(data["badges"][-1]["history"][0]["at"], BASE_DATE)
        self.assertIn("new-helper", images)

    def test_upgrade_updates_artwork_and_verifies_the_new_milestone(self):
        saved = previous()
        original = copy.deepcopy(saved)
        client = FakeGitHub(card(count=2), {"pull-shark": detail(count=2)}, {SOURCES[1]: BRONZE_DATE})
        data, images = sync.collect(saved, client)
        badge = data["badges"][0]
        self.assertEqual(badge["history"][0], saved["badges"][0]["history"][0])
        self.assertEqual(badge["history"][1]["at"], BRONZE_DATE)
        self.assertEqual(badge["history"][1]["milestone"], "16 merged pull requests")
        self.assertEqual(client.date_requests, [SOURCES[1]])
        self.assertIn("pull-shark", images)
        self.assertEqual(saved, original)

    def test_gold_tier_is_rendered_inside_a_taller_card(self):
        client = FakeGitHub(card(count=4), {"pull-shark": detail(count=4)}, {SOURCES[3]: GOLD_DATE})
        data, images = sync.collect(previous(3), client)
        badge = data["badges"][0]
        svg = achievements.render_card(badge, images["pull-shark"])
        tree = ElementTree.fromstring(svg)
        self.assertGreater(int(tree.attrib["height"]), 284)
        self.assertIn("Gold milestone", svg)
        self.assertIn("1024 merged pull requests", svg)
        self.assertIn("17 Nov 2026", svg)

    def test_recorded_base_unlock_is_not_replaced_with_a_merge_date(self):
        client = FakeGitHub(card("pair-extraordinaire", name="Pair Extraordinaire"),
                            {"pair-extraordinaire": detail("pair-extraordinaire", timestamp="2026-10-03T14:18:19Z")},
                            {SOURCES[0]: "2026-09-26T11:02:09Z"})
        data, _ = sync.collect({"username": USER, "badges": []}, client)
        self.assertEqual(data["badges"][0]["history"][0]["at"], "2026-10-03T14:18:19Z")
        self.assertEqual(client.date_requests, [])

    def test_long_new_badge_labels_fit_the_card(self):
        badge = previous()["badges"][0]
        badge["name"] = "A Newly Introduced GitHub Achievement"
        badge["history"][0]["milestone"] = "Earned a newly introduced GitHub badge with a longer milestone description"
        svg = ElementTree.fromstring(achievements.render_card(badge, PNG))
        lines = [node.text for node in svg.iter() if node.attrib.get("class") == "muted"]
        self.assertEqual(len(lines), 3)  # Two subtitle lines plus the footer.
        self.assertLessEqual(len(lines[0]), 43)
        self.assertLessEqual(len(lines[1]), 43)

    def test_unpublished_milestone_date_is_not_invented(self):
        client = FakeGitHub(card(count=2), {"pull-shark": detail(count=2)})
        data, images = sync.collect(previous(), client)
        item = data["badges"][0]["history"][1]
        self.assertIsNone(item["at"])
        self.assertEqual(item["date_basis"], "unavailable")
        svg = achievements.render_card(data["badges"][0], images["pull-shark"])
        self.assertIn("Not published", svg)

    def test_incomplete_overview_cannot_erase_saved_badges(self):
        with self.assertRaisesRegex(ValueError, "No earned achievement"):
            sync.collect(previous(), FakeGitHub('<h1>Temporarily unavailable</h1>'))
        with self.assertRaisesRegex(ValueError, "fewer badges"):
            sync.collect(previous(), FakeGitHub(card("new-helper")))

    def test_incomplete_history_cannot_publish_an_upgrade(self):
        client = FakeGitHub(card(count=2), {"pull-shark": detail(count=1)})
        with self.assertRaisesRegex(ValueError, "Incomplete badge detail"):
            sync.collect(previous(), client)

    def test_lower_tier_response_preserves_saved_history(self):
        with self.assertRaisesRegex(ValueError, "fewer tiers"):
            sync.collect(previous(3), FakeGitHub(card(count=2)))

    def test_failed_artwork_download_does_not_change_any_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / "assets/achievements/history.json"
            state.parent.mkdir(parents=True)
            state.write_text(json.dumps(previous()))
            (root / "README.md").write_text(achievements.BEGIN + '\n' + achievements.END)
            (state.parent / "pull-shark.png").write_bytes(PNG)
            before = {path: path.read_bytes() for path in root.rglob('*') if path.is_file()}
            client = FakeGitHub(card(count=2), {"pull-shark": detail(count=2)},
                                {SOURCES[1]: BRONZE_DATE}, artwork=b'Not a PNG')
            with patch.object(sync, "ROOT", root), patch.object(sync, "STATE", state), \
                 patch.object(sync, "GitHub", return_value=client), patch.object(sys, "argv", ["sync"]):
                with self.assertRaisesRegex(ValueError, "Invalid badge artwork"):
                    sync.main()
            after = {path: path.read_bytes() for path in root.rglob('*') if path.is_file()}
            self.assertEqual(before, after)

    def test_new_tier_timestamp_from_github_takes_precedence(self):
        html = detail(count=2).replace('<span>16th', '<relative-time datetime="2026-09-17T01:00:00Z"></relative-time><span>16th')
        client = FakeGitHub(card(count=2), {"pull-shark": html}, {SOURCES[1]: BRONZE_DATE})
        data, _ = sync.collect(previous(), client)
        item = data["badges"][0]["history"][1]
        self.assertEqual(item["at"], "2026-09-17T01:00:00Z")
        self.assertEqual(item["date_basis"], "github_tier_unlock")
        self.assertEqual(client.date_requests, [])

    def test_changed_accepted_answer_is_not_used_as_the_old_milestone(self):
        client = sync.GitHub()
        source = "https://github.com/Antech-greyhat/Learn.py/discussions/62#discussioncomment-19675583"
        response = {"repository": {"discussion": {"answerChosenAt": GOLD_DATE,
                    "answer": {"url": source + '-different'}}}}
        with patch.object(client, "graphql", return_value=response):
            self.assertIsNone(client.activity_date(source))

    def test_timezone_conversion_and_readme_markers(self):
        self.assertEqual(achievements.date_label("2026-11-16T22:30:00Z"), "17 Nov 2026")
        with self.assertRaises(ValueError):
            achievements.validate_markers(achievements.END + achievements.BEGIN)


if __name__ == "__main__":
    unittest.main()
