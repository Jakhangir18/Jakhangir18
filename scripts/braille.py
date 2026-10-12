#!/usr/bin/env python3
"""Write assets/braille-{light,dark}.svg: a line of Grade 1 Braille whose raised dots
press in one after another, a nod to TouchPoint. Run from the repo root:
    python3 scripts/braille.py "jakhangir tynshimov"
"""
import sys
from pathlib import Path

DOTS = {
    "a": "1", "b": "12", "c": "14", "d": "145", "e": "15", "f": "124", "g": "1245",
    "h": "125", "i": "24", "j": "245", "k": "13", "l": "123", "m": "134", "n": "1345",
    "o": "135", "p": "1234", "q": "12345", "r": "1235", "s": "234", "t": "2345",
    "u": "136", "v": "1236", "w": "2456", "x": "1346", "y": "13456", "z": "1356",
}
# Dot number -> (column, row) inside a cell.
POS = {"1": (0, 0), "2": (0, 1), "3": (0, 2), "4": (1, 0), "5": (1, 1), "6": (1, 2)}
THEMES = {"light": ("#0d0d0d", "#d9d9d6"), "dark": ("#f0f0ee", "#30363d")}

PITCH, CELL, R, STEP = 14, 42, 4.2, 0.06  # dot spacing, cell advance, radius, seconds per dot


def svg(text, ink, flat):
    cells = [c for c in text.lower() if c == " " or c in DOTS]
    width = len(cells) * CELL + 20
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="56" '
           f'viewBox="0 0 {width} 56" role="img"><title>{text} in Grade 1 Braille</title>']
    n = 0
    for i, c in enumerate(cells):
        if c == " ":
            continue
        x0 = 10 + i * CELL
        for d, (col, row) in POS.items():
            cx, cy = x0 + col * PITCH + R, 10 + row * PITCH + R
            if d in DOTS[c]:
                out.append(
                    f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{R}" fill="{ink}" opacity="0.12">'
                    f'<animate attributeName="opacity" from="0.12" to="1" dur="0.35s" '
                    f'begin="{0.4 + n * STEP:.2f}s" fill="freeze"/></circle>')
                n += 1
            else:
                out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{R * 0.45:.2f}" fill="{flat}"/>')
    out.append("</svg>")
    return "\n".join(out)


def main():
    text = sys.argv[1] if len(sys.argv) > 1 else "jakhangir tynshimov"
    for theme, (ink, flat) in THEMES.items():
        Path(f"assets/braille-{theme}.svg").write_text(svg(text, ink, flat) + "\n")


if __name__ == "__main__":
    main()
