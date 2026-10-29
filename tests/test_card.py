"""Run with:  python -m unittest discover tests

No network needed: the GitHub API is replaced by a fake `run` function that
answers each query from a small script of canned responses.
"""

import datetime as dt
import sys
import tempfile
import tomllib
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import build_card       # noqa: E402
import github_stats     # noqa: E402


class UptimeTests(unittest.TestCase):
    def test_year_only(self):
        self.assertEqual(build_card.uptime_text("2014", dt.date(2026, 10, 29)),
                         "12 years (since 2014)")

    def test_full_date(self):
        self.assertEqual(build_card.uptime_text("2000-01-15", dt.date(2026, 10, 29)),
                         "26 years, 9 months, 14 days")

    def test_borrows_days_and_months(self):
        # 31 Jan -> 1 Mar 2026: one month back is February (28 days)
        self.assertEqual(build_card.uptime_text("2025-01-31", dt.date(2026, 3, 1)),
                         "1 year, 1 month, 1 day")


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.config = tomllib.loads((ROOT / "profile.toml").read_text(encoding="utf-8"))
        self.width = self.config["card"]["line_width"]
        self.stats = {"repos": 4, "contributed": 6, "stars": 12, "commits": 1234,
                      "followers": 7, "loc_added": 50000, "loc_deleted": 4000}

    def test_every_line_is_exactly_line_width(self):
        lines = build_card.info_lines(self.config, self.stats, dt.date(2026, 10, 29))
        for pieces in lines:
            if len(pieces) <= 1:        # blank rows (". ") and blank lines
                continue
            text = "".join(t for t, _ in pieces)
            self.assertEqual(len(text), self.width, text)

    def test_missing_stats_show_question_marks(self):
        lines = build_card.info_lines(self.config, None, dt.date(2026, 10, 29))
        stats_text = "".join(t for p in lines[-3:] for t, _ in p)
        self.assertIn("?", stats_text)

    def test_tall_portrait_is_scaled_to_text_height(self):
        lines = build_card.info_lines(self.config, self.stats, dt.date(2026, 10, 29))
        portrait = ["@" * 80] * (len(lines) * 2)          # twice as many rows as text
        self.assertEqual(build_card.portrait_scale(portrait, lines), 0.5)
        svg = build_card.render_svg(portrait, lines, self.width, "dark")
        root = ET.fromstring(svg.split("?>", 1)[1])
        ns = "{http://www.w3.org/2000/svg}"
        portrait_text, info_text = root.findall(f"{ns}text")
        last_portrait_y = float(portrait_text.findall(f"{ns}tspan")[-1].get("y"))
        last_text_y = float(info_text.findall(f"{ns}tspan")[-1].get("y"))
        self.assertAlmostEqual(last_portrait_y, last_text_y, delta=build_card.LINE_H)
        self.assertEqual(portrait_text.get("font-size"), "8px")

    def test_dark_card_uses_its_own_portrait_when_there_is_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ascii.txt").write_text("light\n")
            self.assertEqual(build_card.load_ascii("dark", root), ["light"])   # fallback
            (root / "ascii_dark.txt").write_text("dark\n\n")
            self.assertEqual(build_card.load_ascii("dark", root), ["dark", ""])  # blank row kept
            self.assertEqual(build_card.load_ascii("light", root), ["light"])

    def test_short_portrait_is_never_enlarged(self):
        self.assertEqual(build_card.portrait_scale(["x"] * 5, [[]] * 26), 1.0)

    def test_svg_is_valid_xml_and_escapes_ascii(self):
        lines = build_card.info_lines(self.config, self.stats, dt.date(2026, 10, 29))
        svg = build_card.render_svg(["<&>"], lines, self.width, "dark")
        root = ET.fromstring(svg.split("?>", 1)[1])
        self.assertTrue(root.tag.endswith("svg"))


def fake_api(responses):
    """Return a `run` function that answers queries in order and records them."""
    calls = []

    def run(query, variables):
        calls.append((query, dict(variables)))
        return responses.pop(0)
    return run, calls


def repos_page(nodes, has_next, cursor=None, total=3):
    return {"user": {"repositories": {
        "totalCount": total,
        "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
        "nodes": nodes}}}


def history_page(commits, has_next, cursor=None):
    return {"repository": {"defaultBranchRef": {"target": {"history": {
        "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
        "nodes": [{"additions": a, "deletions": d} for a, d in commits]}}}}}


class GitHubStatsTests(unittest.TestCase):
    def test_collect_follows_every_page_and_adds_it_all_up(self):
        mine = lambda name, stars: {"nameWithOwner": f"me/{name}",  # noqa: E731
                                    "stargazerCount": stars, "owner": {"login": "me"}}
        theirs = {"nameWithOwner": "friend/tool", "stargazerCount": 99,
                  "owner": {"login": "friend"}}
        run, calls = fake_api([
            {"user": {"id": "U1", "createdAt": "2025-06-01T00:00:00Z",
                      "followers": {"totalCount": 5}}},
            repos_page([mine("a", 2), theirs], True, "c1"),         # repos, page 1
            repos_page([mine("b", 1)], False),                        # repos, page 2
            history_page([(100, 10), (50, 5)], True, "h1"),           # me/a, page 1
            history_page([(10, 1)], False),                           # me/a, page 2
            history_page([(7, 7)], False),                            # friend/tool
            {"repository": {"defaultBranchRef": None}},               # me/b is empty
            {"user": {"contributionsCollection": {"totalCommitContributions": 40}}},
            {"user": {"contributionsCollection": {"totalCommitContributions": 2}}},
        ])
        stats = github_stats.collect(
            "me", run=run, now=dt.datetime(2026, 10, 29, tzinfo=dt.timezone.utc))

        self.assertEqual(stats["repos"], 2)          # only the ones I own
        self.assertEqual(stats["contributed"], 3)    # owned + contributed to
        self.assertEqual(stats["stars"], 3)          # friend's 99 stars don't count
        self.assertEqual(stats["followers"], 5)
        self.assertEqual(stats["loc_added"], 167)
        self.assertEqual(stats["loc_deleted"], 23)
        self.assertEqual(stats["commits"], 42)       # two one-year windows
        self.assertEqual(calls[2][1]["cursor"], "c1")  # really asked for page 2

    def test_public_only_sends_privacy_filter(self):
        run, calls = fake_api([repos_page([], False, total=0)])
        github_stats.fetch_repos("me", include_private=False, run=run)
        self.assertEqual(calls[0][1]["privacy"], "PUBLIC")

    def test_unknown_user_is_a_clear_error(self):
        run, _ = fake_api([{"user": None}])
        with self.assertRaises(github_stats.GitHubError):
            github_stats.fetch_user("nobody", run)


try:
    from PIL import Image
    import ascii_portrait
except ImportError:      # the GitHub Action doesn't install Pillow; these run on your PC
    Image = None


@unittest.skipIf(Image is None, "Pillow not installed")
class PortraitTests(unittest.TestCase):
    def test_background_is_blank_and_ink_is_dense(self):
        img = Image.new("L", (10, 10), 255)            # white background...
        img.paste(0, (0, 0, 5, 10))                    # ...left half black
        lines = ascii_portrait.to_ascii(img, 2, 1, invert=True)
        self.assertEqual(lines, [ascii_portrait.RAMP[-1]])   # "@", then trailing blank stripped

    def test_gamma_quietens_mid_tones(self):
        grey = Image.new("L", (4, 4), 128)
        plain = ascii_portrait.to_ascii(grey, 1, 1, invert=True)[0]
        quiet = ascii_portrait.to_ascii(grey, 1, 1, invert=True, gamma=2)[0]
        ramp = ascii_portrait.RAMP
        self.assertLess(ramp.index(quiet), ramp.index(plain))

    def test_background_cut_out_stops_at_the_outline(self):
        from PIL import ImageDraw
        img = Image.new("L", (400, 400), 240)                     # light background
        ImageDraw.Draw(img).ellipse((100, 100, 300, 300), fill=230, outline=0, width=12)
        mask = ascii_portrait.background_mask(img)
        self.assertEqual(mask.getpixel((20, 20)), 0)              # background found
        self.assertEqual(mask.getpixel((200, 200)), 255)          # light inside the outline kept

    def test_crop_matches_grid_shape(self):
        img = Image.new("L", (1440, 1440))
        out = ascii_portrait.crop_to_grid(img, 80, 52, 0)
        self.assertAlmostEqual(out.width / out.height,
                               80 * ascii_portrait.CELL_ASPECT / 52, places=2)


if __name__ == "__main__":
    unittest.main()
