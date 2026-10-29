"""Build dark_mode.svg and light_mode.svg for the GitHub profile README.

Inputs:   profile.toml          your text (edit this)
          ascii.txt             ASCII portrait for the light card (ascii_portrait.py)
          ascii_dark.txt        ASCII portrait for the dark card (optional)
          GitHub GraphQL API    live stats (via github_stats.py)
Outputs:  dark_mode.svg, light_mode.svg, stats.json (last good stats)

Run it:   python scripts/build_card.py            (live stats if ACCESS_TOKEN is set)
          python scripts/build_card.py --offline  (skip the API, reuse stats.json)

The card is rebuilt from scratch every run, so there is no SVG to keep in sync.
"""

import argparse
import calendar
import datetime as dt
import json
import os
import sys
import tomllib
from pathlib import Path
from xml.sax.saxutils import escape

import github_stats

ROOT = Path(__file__).resolve().parent.parent

# --- Layout ----------------------------------------------------------------
# GitHub shows the SVG as an image, so it uses the viewer's own monospace font.
# 9.7px per character at 16px fits DejaVu Sans Mono / Menlo / Courier; Consolas
# (Windows) is a bit narrower and just gets a little more breathing room.
FONT_SIZE = 16
CHAR_W = 9.7
LINE_H = 20
PAD = 15
GAP_CHARS = 3            # space between the portrait and the text column

# --- Colours (GitHub's own palette, plus a green accent for the headings) ---
THEMES = {
    "dark": {"bg": "#161b22", "text": "#c9d1d9", "key": "#ffa657", "value": "#a5d6ff",
             "dots": "#616e7f", "accent": "#3fb950", "add": "#3fb950", "del": "#f85149"},
    "light": {"bg": "#f6f8fa", "text": "#24292f", "key": "#953800", "value": "#0a3069",
              "dots": "#c2cfde", "accent": "#1a7f37", "add": "#1a7f37", "del": "#cf222e"},
}


# ===========================================================================
# 1. Uptime
# ===========================================================================

def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def uptime_text(since, today):
    """'2014' -> '12 years (since 2014)'; '1990-05-17' -> '36 years, 5 months, 12 days'."""
    if len(since) == 4:
        return f"{plural(today.year - int(since), 'year')} (since {since})"

    start = dt.date.fromisoformat(since)
    # Count whole months first, then the leftover days from that anchor date.
    months = (today.year - start.year) * 12 + today.month - start.month
    if today.day < start.day:
        months -= 1
    year, month = divmod(start.month - 1 + months, 12)
    year, month = start.year + year, month + 1
    # 31 Jan + 1 month has no 31st, so clip to the last day of that month.
    anchor = dt.date(year, month, min(start.day, calendar.monthrange(year, month)[1]))
    days = (today - anchor).days
    years, months = divmod(months, 12)
    return f"{plural(years, 'year')}, {plural(months, 'month')}, {plural(days, 'day')}"


# ===========================================================================
# 2. Stats: live from GitHub, falling back to the last good numbers
# ===========================================================================

def get_stats(card, offline):
    cache = ROOT / "stats.json"
    token = os.environ.get("ACCESS_TOKEN")

    if not offline and token:
        try:
            stats = github_stats.collect(card["github_user"], token,
                                         include_private=card.get("include_private", True))
            cache.write_text(json.dumps(stats, indent=2) + "\n")
            print(f"live stats: {stats}")
            return stats
        except Exception as err:  # keep building the card even if GitHub is having a bad day
            # "::warning::" makes this show up as a yellow note in the Actions run summary.
            print(f"::warning::Could not fetch live GitHub stats ({err}). Using last saved numbers.")
    elif not offline:
        print("note: ACCESS_TOKEN is not set, using last saved numbers")

    if cache.exists():
        return json.loads(cache.read_text())
    return None


# ===========================================================================
# 3. Text lines for the right-hand column
#
# A "line" is a list of pieces: (text, css_class). css_class None = plain text.
# Every line is padded with dots to exactly `width` characters, which is what
# keeps all the values lined up on the right.
# ===========================================================================

def length(pieces):
    return sum(len(text) for text, _ in pieces)


def key_pieces(key):
    """'Languages.Real' -> Languages . Real, with the dot in the plain colour."""
    pieces = []
    for i, part in enumerate(key.split(".")):
        if i:
            pieces.append((".", None))
        pieces.append((part, "key"))
    return pieces


def dotted(left, right, width):
    """left + ' ..... ' + right, padded to `width` characters."""
    n_dots = width - length(left) - length(right) - 2
    if n_dots < 1:
        text = "".join(t for t, _ in left + right)
        print(f"warning: line is {1 - n_dots} char(s) too long, shorten it: {text!r}")
        n_dots = 1
    return left + [(" " + "." * n_dots + " ", "dots")] + right


def row(key, value, width):
    left = [(". ", "dots")] + key_pieces(key) + [(":", None)]
    return dotted(left, [(value, "value")], width)


def heading(title, width):
    label = f"- {title} " if title else ""
    return [(label, "accent"), ("─" * (width - len(label)), "dots")]


def stat_pair(left_key, left_value, right_key, right_value, width):
    """Two stats on one line, split by ' | ', like the original card."""
    left_width = width // 2 + 4
    left = dotted([(". ", "dots")] + key_pieces(left_key) + [(":", None)],
                  left_value, left_width)
    right = dotted(key_pieces(right_key) + [(":", None)],
                   right_value, width - left_width - 3)
    return left + [(" | ", None)] + right


def number(value):
    return "?" if value is None else f"{value:,}"


def stats_lines(stats, width):
    s = stats or {}
    get = lambda k: number(s.get(k))  # noqa: E731
    repos = [(get("repos"), "value"), (" {", None), ("Contributed", "key"),
             (": ", None), (get("contributed"), "value"), ("}", None)]
    added, deleted = s.get("loc_added"), s.get("loc_deleted")
    total = None if added is None else added - deleted
    loc = [(number(total), "value"), (" ( ", None),
           (number(added) + "++", "add"), (", ", None),
           (number(deleted) + "--", "del"), (" )", None)]
    return [
        stat_pair("Repos", repos, "Stars", [(get("stars"), "value")], width),
        stat_pair("Commits", [(get("commits"), "value")],
                  "Followers", [(get("followers"), "value")], width),
        dotted([(". ", "dots")] + key_pieces("Lines of Code on GitHub") + [(":", None)],
               loc, width),
    ]


def info_lines(config, stats, today):
    card = config["card"]
    width = card["line_width"]
    uptime = uptime_text(str(card["uptime_since"]), today)

    lines = [[(card["title"], "accent"), (" ", None),
              ("─" * (width - len(card["title"]) - 1), "dots")]]
    for i, section in enumerate(config["section"]):
        if section.get("heading"):
            if i:
                lines.append([])                       # blank line before a heading
            lines.append(heading(section["heading"], width))
        if section.get("stats"):
            lines.extend(stats_lines(stats, width))
        for r in section.get("rows", []):
            if not r:
                lines.append([(". ", "dots")])         # blank row keeps the dot column
            else:
                lines.append(row(r[0], r[1].replace("{uptime}", uptime), width))
    return lines


# ===========================================================================
# 4. SVG
# ===========================================================================

def tspans(pieces):
    out = []
    for text, cls in pieces:
        text = escape(text)
        out.append(f'<tspan class="{cls}">{text}</tspan>' if cls else text)
    return "".join(out)


def portrait_scale(ascii_lines, lines):
    """Shrink a tall portrait so it is exactly as tall as the text column.
    52 portrait rows next to 26 text lines -> drawn at half size (8px font)."""
    if not ascii_lines:
        return 1.0
    return min(1.0, len(lines) / len(ascii_lines))


def render_svg(ascii_lines, lines, width_chars, theme):
    c = THEMES[theme]
    scale = portrait_scale(ascii_lines, lines)
    ascii_cols = max((len(a) for a in ascii_lines), default=0)
    portrait_w = ascii_cols * CHAR_W * scale
    text_x = PAD + portrait_w + GAP_CHARS * CHAR_W if ascii_cols else PAD
    width = round(text_x + width_chars * CHAR_W + PAD)
    height = round(PAD + max(len(ascii_lines) * scale, len(lines)) * LINE_H + PAD // 2)

    def y(i, s=1.0):
        return round(PAD + ((i + 1) * LINE_H - 5) * s, 1)

    portrait = "\n".join(f'<tspan x="{PAD}" y="{y(i, scale)}">{escape(a)}</tspan>'
                         for i, a in enumerate(ascii_lines))
    info = "\n".join(f'<tspan x="{text_x:.1f}" y="{y(i)}">{tspans(p)}</tspan>'
                     for i, p in enumerate(lines))

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"
     font-family="Consolas, 'DejaVu Sans Mono', Menlo, 'Courier New', monospace" font-size="{FONT_SIZE}px">
<style>
text, tspan {{ white-space: pre; }}
.key {{ fill: {c['key']}; }}
.value {{ fill: {c['value']}; }}
.dots {{ fill: {c['dots']}; }}
.accent {{ fill: {c['accent']}; font-weight: bold; }}
.add {{ fill: {c['add']}; }}
.del {{ fill: {c['del']}; }}
</style>
<rect width="{width}" height="{height}" rx="15" fill="{c['bg']}"/>
<text xml:space="preserve" fill="{c['text']}" font-size="{FONT_SIZE * scale:g}px">
{portrait}
</text>
<text xml:space="preserve" fill="{c['text']}">
{info}
</text>
</svg>
"""


# ===========================================================================
# 5. Main
# ===========================================================================

def load_ascii(theme, root=ROOT):
    """Dark card uses ascii_dark.txt if there is one; everything else uses ascii.txt."""
    path = root / "ascii_dark.txt"
    if theme != "dark" or not path.exists():
        path = root / "ascii.txt"
    # splitlines keeps blank rows at the bottom; they count towards the portrait's height.
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--offline", action="store_true", help="don't call the GitHub API")
    args = parser.parse_args(argv)

    config = tomllib.loads((ROOT / "profile.toml").read_text(encoding="utf-8"))
    stats = get_stats(config["card"], args.offline)
    lines = info_lines(config, stats, dt.date.today())
    for theme in THEMES:
        svg = render_svg(load_ascii(theme), lines, config["card"]["line_width"], theme)
        (ROOT / f"{theme}_mode.svg").write_text(svg, encoding="utf-8")
        print(f"wrote {theme}_mode.svg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
