#!/usr/bin/env python3
"""Draw assets/world-{light,dark}.svg, a pixel valley grown from my commit history, and
refresh the caption between <!-- world:start --> and <!-- world:end --> in README.md.

The weather follows the rules of commitweather (scripts/climate.py): steady work brings
summer, silence brings fog. Each tree is one week of the past six months, oldest on the
left; its height is that week's contributions, and a week with none leaves a gap.

Run daily by .github/workflows/recent.yml from the repo root:
    GITHUB_TOKEN=... python3 scripts/world.py
    python3 scripts/world.py --preview DIR   # the five biomes with made-up data, no network
"""
from __future__ import annotations

import math
import os
import random
import re
import sys
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from pathlib import Path

import climate

USER = "Jakhangir18"
B = 12                      # block size, px
COLS, ROWS = 104, 26
W, H = COLS * B, ROWS * B
GROUND = 21 * B             # y of the ground surface
S = B // 2                  # trees are drawn on a half-block grid
SLOT = W // climate.WEEKS   # px of ground each week's tree stands on
CROWN = 5 * S               # height of a tree's crown
NIGHT = "#0b1030"

# Colours are the ones commitweather's layers use for each weather.
PALETTE = {
    "sunny": {
        "sky": ((0, "#5d1a4a"), (.1, "#8a1f6e"), (.25, "#d04545"), (.45, "#ff5722"),
                (.65, "#ffb300"), (1, "#ffc857")),
        "rock": ("#e8d7a8", "#c2b28a", "#8d8b86"), "soil": ("#f2d59b", "#d2b27b", "#b89b6a"),
        "tree": ("#6d4c41", "#7cb342", "#9ccc65", "#558b2f"), "water": ("#4fc3f7", "#0288d1"),
        "sun": ("#ffd54f", "#fff9c4")},
    "wind": {
        "sky": ((0, "#4f8fd6"), (.2, "#6ea7e6"), (.4, "#8bbdef"), (.6, "#a7cdf6"),
                (.8, "#c8defb"), (1, "#f4d6e6")),
        "rock": ("#66bb6a", "#6d4c41", "#455a64"), "soil": ("#66bb6a", "#795548", "#546e7a"),
        "tree": ("#4e342e", "#43a047", "#66bb6a", "#2e7d32"), "water": ("#42a5f5", "#1565c0"),
        "sun": ("#fff59d", "#fffde7")},
    "rain": {
        "sky": ((0, "#0a0a1a"), (.2, "#1a1a3e"), (.4, "#2d3561"), (.6, "#3d4f7c"),
                (.8, "#546e8a"), (1, "#37474f")),
        "rock": ("#4caf50", "#5d4037", "#37474f"), "soil": ("#2e7d32", "#5d4037", "#37474f"),
        "tree": ("#4e342e", "#2e7d32", "#388e3c", "#1b5e20"), "water": ("#1565c0", "#0a3670"),
        "sun": None},
    "snow": {
        "sky": ((0, "#cfd8dc"), (.2, "#b0bec5"), (.4, "#90a4ae"), (.6, "#b0bec5"),
                (.8, "#cfd8dc"), (1, "#eceff1")),
        "rock": ("#eceff1", "#b0bec5", "#78909c"), "soil": ("#eceff1", "#b0bec5", "#78909c"),
        "tree": ("#5d4037", "#2e7d32", "#fafafa", "#1b5e20"), "water": ("#b3e5fc", "#4fc3f7"),
        "sun": ("#eceff1", "#ffffff")},
    "fog": {
        "sky": ((0, "#2c1810"), (.15, "#4a2c20"), (.35, "#6b4423"), (.55, "#8b5a3c"),
                (.8, "#a67c52"), (1, "#9d7e6f")),
        "rock": ("#e8cb9b", "#d2b48c", "#a67b5b"), "soil": ("#dcb889", "#b18e63", "#8b5a3c"),
        "tree": ("#8d6e63", "#9ccc65", "#aed581", "#7cb342"), "water": ("#6b4423", "#4a2c20"),
        "sun": None},
}
PARTICLE = {"sunny": "dust", "wind": "cloud", "rain": "rain", "snow": "snow", "fog": "fog"}

STYLE = """
.dust{animation:dust 9s linear infinite}
.rain{animation:fall 1.1s linear infinite}
.snow{animation:fall 9s linear infinite}
.fog{animation:slide 40s ease-in-out infinite alternate}
.cloud{animation:drift 90s linear infinite}
.blink{animation:blink 3s ease-in-out infinite alternate}
.flag{animation:wave 1.4s ease-in-out infinite alternate;transform-box:fill-box;transform-origin:left center}
@keyframes dust{0%{transform:translate(0,0);opacity:0}15%{opacity:.9}100%{transform:translate(60px,-90px);opacity:0}}
@keyframes fall{to{transform:translate(-40px,340px)}}
@keyframes slide{to{transform:translateX(140px)}}
@keyframes drift{from{transform:translateX(-300px)}to{transform:translateX(1300px)}}
@keyframes blink{from{opacity:.15}to{opacity:1}}
@keyframes wave{to{transform:skewY(-14deg)}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
"""


def mix(a: str, b: str, t: float) -> str:
    """Blend hex colour a toward b by t (0 = a, 1 = b)."""
    channels = [(int(a[i:i + 2], 16), int(b[i:i + 2], 16)) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in channels)


def rect(x: float, y: float, w: float, h: float, fill: str, extra: str = "") -> str:
    return f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" fill="{fill}"{extra}/>'


def ridge(rng: random.Random, low: int, high: int) -> list[int]:
    """Height in blocks of a mountain range at each column: three waves and one main peak."""
    peak = rng.uniform(.3, .8) * COLS
    waves = [(rng.uniform(.03, .12), rng.uniform(0, math.tau), rng.uniform(.4, 1)) for _ in range(3)]
    weight = sum(a for _, _, a in waves)
    heights = []
    for col in range(COLS):
        wave = sum(a * math.sin(f * col + p) for f, p, a in waves) / weight
        bump = math.exp(-((col - peak) / (COLS * .16)) ** 2)
        t = min(1.0, max(0.0, .3 + .25 * wave + .6 * bump))
        heights.append(round(low + (high - low) * t))
    return heights


def runs(heights: list[int]) -> list[tuple[int, int, int]]:
    """Merge neighbouring columns of equal height into (first column, columns, height)."""
    out: list[tuple[int, int, int]] = []
    for col, h in enumerate(heights):
        if out and out[-1][2] == h:
            out[-1] = (out[-1][0], out[-1][1] + 1, h)
        else:
            out.append((col, 1, h))
    return out


def mountains(heights: list[int], top: str, mid: str, base: str, textured: bool) -> list[str]:
    out, outline = [], [f"M0 {GROUND}"]
    for col, n, h in runs(heights):
        x, y, w = col * B, GROUND - h * B, n * B
        out.append(rect(x, y, w, h * B, base))
        out.append(rect(x, y, w, min(h, 1) * B, top))
        if h > 1:
            out.append(rect(x, y + B, w, B, mid))
        outline.append(f"V{y}H{x + w}")
    if textured:
        out.append(f'<path d="{"".join(outline)}V{GROUND}Z" fill="url(#grid)"/>')
    return out


def ground(rng: random.Random, soil: Sequence[str], water: Sequence[str]) -> list[str]:
    grass, dirt, stone = soil
    out = [rect(0, GROUND, W, B, grass), rect(0, GROUND + B, W, 2 * B, dirt),
           rect(0, GROUND + 3 * B, W, 2 * B, stone)]
    first = rng.randrange(6, COLS - 40)
    span = rng.randrange(20, 30)
    out.append(rect(first * B, GROUND + 2 * B, span * B, B, water[0]))
    out.append(rect((first + 1) * B, GROUND + 3 * B, (span - 2) * B, B, water[1]))
    for _ in range(7):
        x = (first + 1 + rng.randrange(span - 3)) * B
        out.append(rect(x, GROUND + 2 * B, B, S / 2, "#ffffff",
                        f' opacity=".6" class="blink" style="animation-duration:{rng.uniform(2, 5):.1f}s"'))
    out.append(rect(0, GROUND, W, 5 * B, "url(#grid)"))
    return out


def trunk_height(count: int, busiest: int) -> int:
    """Trunk height in px for a week; 0 for a week without contributions."""
    if count <= 0 or busiest <= 0:
        return 0
    return S * (3 + round(12 * math.sqrt(count / busiest)))


def trees(weeks: Sequence[int], colours: Sequence[str]) -> list[str]:
    trunk, leaves, light, dark = colours
    busiest = max(weeks, default=0)
    out = []
    for i, count in enumerate(weeks):
        th = trunk_height(count, busiest)
        if not th:
            continue
        x, top = i * SLOT + S, GROUND - th  # the crown is six half-blocks wide, centred
        out.append(
            f'<g class="tree"><title>{count} contributions</title>'
            + rect(x + 2 * S, top, B, th, trunk)
            + rect(x + 2 * S, top - 5 * S, B, S, light)
            + rect(x + S, top - 4 * S, 4 * S, S, leaves)
            + rect(x + S, top - 4 * S, B, S, light)
            + rect(x, top - 3 * S, 6 * S, B, leaves)
            + rect(x + 5 * S, top - 3 * S, S, B, dark)
            + rect(x + S, top - S, 4 * S, S, dark) + "</g>")
    return out


def flag(weeks: Sequence[int]) -> str:
    """A pennant over the newest week, the last slot."""
    th = trunk_height(weeks[-1], max(weeks)) if weeks else 0
    x = max(len(weeks) - 1, 0) * SLOT + SLOT // 2 - 1
    top = GROUND - th - (CROWN if th else 0)
    return (rect(x, top - 22, 2, 22, "#eceff1")
            + f'<path class="flag" d="M{x + 2} {top - 22}h14l-4 5 4 5h-14z" fill="#ef5350" '
              'stroke="#ffffff"/>')


def sky_things(rng: random.Random, mood: str, night: bool, sun) -> list[str]:
    out = []
    if night:
        for _ in range(46):
            out.append(rect(rng.randrange(W), rng.randrange(int(H * .5)), 3, 3, "#ffffff",
                            f' class="blink" style="animation-duration:{rng.uniform(2, 6):.1f}s"'))
        sun = ("#cfd8dc", "#eceff1")  # the moon rises in any weather
    if sun:
        cx, cy = round(W * .36), 5 * B
        if mood == "sunny" and not night:
            for dy in (-150, -40, 90):
                out.append(f'<path d="M{cx} {cy}L{W} {cy + dy}V{cy + dy + 70}Z" fill="#fff3c0" opacity=".1"/>')
        out.append(rect(cx - 5 * B, cy - 5 * B, 10 * B, 10 * B, sun[0],
                        ' opacity=".22" class="blink" style="animation-duration:6s"'))
        out.append(rect(cx - 2.5 * B, cy - 2.5 * B, 5 * B, 5 * B, sun[0]))
        out.append(rect(cx - 1.5 * B, cy - 1.5 * B, 3 * B, 3 * B, sun[1]))
    return out


def weather(rng: random.Random, mood: str, night: bool) -> list[str]:
    kind = PARTICLE[mood]

    def moving(shape: str, seconds: float) -> str:
        return shape.replace("/>", f' class="{kind}" style="animation-duration:{seconds:.1f}s;'
                                   f'animation-delay:-{rng.uniform(0, seconds):.1f}s"/>', 1)

    out = []
    if kind == "dust":
        for _ in range(26):
            out.append(moving(rect(rng.randrange(W), rng.randrange(60, GROUND), 4, 4, "#ffd54f",
                                   ' opacity=".7"'), rng.uniform(7, 13)))
    elif kind == "rain":
        for _ in range(70):
            x = rng.randrange(W + 40)
            out.append(moving(f'<path d="M{x} -30l-3 16" stroke="#90caf9" stroke-width="2" opacity=".7"/>',
                              rng.uniform(.8, 1.4)))
    elif kind == "snow":
        for _ in range(60):
            out.append(moving(rect(rng.randrange(W + 40), -30, 4, 4, "#ffffff", ' opacity=".9"'),
                              rng.uniform(7, 12)))
    elif kind == "fog":
        for i in range(5):
            out.append(moving(rect(-160, 60 + i * 34, W + 320, 20, "#cfd8dc", ' opacity=".13"'),
                              rng.uniform(30, 50)))
    else:  # cloud
        for _ in range(4):
            y = rng.randrange(1, 7) * B
            out.append(moving(f'<path d="M0 {y + B}h{7 * B}v-{B}h-{B}v-{B}h-{4 * B}v{B}h-{2 * B}z" '
                              'fill="#ffffff" opacity=".85"/>', rng.uniform(70, 110)))
    if night and mood in ("sunny", "wind"):
        for _ in range(14):
            out.append(rect(rng.randrange(W), rng.randrange(GROUND - 90, GROUND - 6), 4, 4, "#e6ee9c",
                            f' class="blink" style="animation-duration:{rng.uniform(1.5, 4):.1f}s"'))
    return out


def render(state: climate.Climate, theme: str, user: str = USER) -> str:
    """One self-contained SVG. theme "dark" draws the same valley at night."""
    night = theme == "dark"
    pal = PALETTE[state.mood]
    terrain = random.Random(user)  # the land depends on the name alone, as in commitweather
    rng = random.Random(f"{user}/{state.mood}/{theme}")

    def land(colours):
        return tuple(mix(c, NIGHT, .45) for c in colours) if night else tuple(colours)

    # At night the sky darkens most at the top and keeps a glow at the horizon.
    sky = [(at, mix(c, NIGHT, .88 - .3 * at) if night else c) for at, c in pal["sky"]]
    rock, soil, wood, water = (land(pal[k]) for k in ("rock", "soil", "tree", "water"))
    far = tuple(mix(c, sky[3][1], .55) for c in rock)
    label = f"{state.biome} · {state.score}/100"
    stops = "".join(f'<stop offset="{at:g}" stop-color="{c}"/>' for at, c in sky)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img">',
        (f"<title>A pixel valley grown from {user}'s commit history: {state.biome}, "
         f"score {state.score} of 100. One tree for each week of the past six months.</title>"),
        f"<style>{STYLE}</style>",
        (f'<defs><linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">{stops}</linearGradient>'
         f'<pattern id="grid" width="{B}" height="{B}" patternUnits="userSpaceOnUse">'
         f'<path d="M{B} 0V{B}H0" fill="none" stroke="#000" stroke-opacity=".1"/></pattern>'
         f'<clipPath id="frame"><rect width="{W}" height="{H}" rx="14"/></clipPath></defs>'),
        '<g clip-path="url(#frame)">',
        rect(0, 0, W, H, "url(#sky)"),
        *sky_things(rng, state.mood, night, pal["sun"]),
        *mountains(ridge(terrain, 4, 11), *far, textured=False),
        *mountains(ridge(terrain, 2, 15), *rock, textured=True),
        *ground(terrain, soil, water),
        *trees(state.weeks, wood),
        flag(state.weeks),
        *weather(rng, state.mood, night),
        rect(14, 14, 24 + 8.6 * len(label), 30, "#000000", ' opacity=".4" rx="6"'),
        ('<text x="26" y="34" font-family="ui-monospace,SFMono-Regular,Menlo,monospace" '
         f'font-size="14" fill="#ffffff">{label}</text>'),
        "</g></svg>",
    ]
    svg = "\n".join(parts) + "\n"
    ET.fromstring(svg)  # a malformed picture must never reach the profile
    return svg


def caption(state: climate.Climate) -> str:
    return (
        "<picture>\n"
        '  <source media="(prefers-color-scheme: dark)" srcset="assets/world-dark.svg">\n'
        f'  <img src="assets/world-light.svg" width="100%" alt="A pixel-art valley grown from my '
        f'commit history: {state.biome}, score {state.score} of 100. One tree for each week of '
        'the past six months.">\n'
        "</picture>\n\n"
        f"<sub><b>{state.biome}, {state.score} of 100.</b> This valley is redrawn every day from "
        'my commits by the rules of <a href="https://github.com/Jakhangir18/commitweather">'
        "commitweather</a>, a project of mine: steady work brings summer, silence brings fog. "
        "Each tree is one week of the past six months and grows with that week's contributions. "
        '<a href="scripts/world.py">How it works</a></sub>')


def rewrite(readme: str, state: climate.Climate) -> str:
    new, n = re.subn(r"(<!-- world:start -->\r?\n).*?(<!-- world:end -->)",
                     lambda m: m.group(1) + caption(state) + "\n" + m.group(2), readme, flags=re.DOTALL)
    if n != 1:
        raise SystemExit("README.md: expected one <!-- world:start --> ... <!-- world:end --> block")
    return new


def preview(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    rng = random.Random(7)
    for limit, name, mood in climate.BIOMES:
        points = 100 if math.isinf(limit) else int(limit) - 5
        weeks = tuple(rng.randrange(2 + points // 3) for _ in range(climate.WEEKS))
        state = climate.Climate(points, name, mood, 0, 0, 0, 0, weeks)
        for theme in ("light", "dark"):
            (folder / f"world-{mood}-{theme}.svg").write_text(render(state, theme))


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "--preview":
        preview(Path(sys.argv[2]))
        return
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is required: the contribution calendar is a GraphQL query")
    state = climate.read(USER, token)
    pictures = {theme: render(state, theme) for theme in ("light", "dark")}
    readme = Path("README.md")
    text = rewrite(readme.read_text(), state)
    for theme, svg in pictures.items():
        Path(f"assets/world-{theme}.svg").write_text(svg)
    readme.write_text(text)
    print(f"{state.biome}, score {state.score}: {state.commits} commits on {state.active_days} days, "
          f"streak {state.streak}, {state.public_repos} public repos")


if __name__ == "__main__":
    main()
