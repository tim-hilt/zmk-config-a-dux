#!/usr/bin/env python3
"""Render a ZMK keymap (arch_dux) as a Miryoku-style keycap cover in SVG.

Usage:
    python3 scripts/keymap_to_svg.py [config/arch_dux.keymap] \
        [-l boards/shields/arch_dux/arch_dux-layouts.dtsi] [-o arch_dux.svg]

Key legends come from the keymap, key positions (column stagger incl. the
dropped pinky columns, thumb cluster) from the ZMK physical layout that
matches the A. Dux PCB.  Every key shows the base-layer legend plus the
legends of the other layers, colour coded per layer.

Only the Python standard library is required.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from xml.sax.saxutils import escape

# --------------------------------------------------------------------------
# keymap parsing
# --------------------------------------------------------------------------

ARITY = {
    "kp": 1,
    "hml": 2,
    "hmr": 2,
    "lt": 2,
    "lt_bspc_del": 2,
    "mo": 1,
    "none": 0,
    "trans": 0,
}

LAYER_RE = re.compile(r"(\w+)\s*\{\s*bindings\s*=\s*<([^>]*)>\s*;", re.S)
PHYS_RE = re.compile(
    r"&key_physical_attrs\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)"
    r"\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)"
)


def strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def parse_bindings(body: str) -> list[tuple[str, list[str]]]:
    """Split a `bindings = <...>;` body into (behavior, params) tuples."""
    tokens = re.findall(r"&\w+|[^\s&]+", body)
    binds: list[tuple[str, list[str]]] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if not tok.startswith("&"):
            i += 1
            continue
        name = tok[1:]
        params = tokens[i + 1 : i + 1 + ARITY.get(name, 0)]
        binds.append((name, params))
        i += 1 + len(params)
    return binds


def read_layers(path: Path) -> list[dict]:
    src = strip_comments(path.read_text())

    # Only look at the keymap node; behavior/macro definitions come before it.
    marker = 'compatible = "zmk,keymap"'
    if marker in src:
        src = src.split(marker, 1)[1]

    layers = []
    for raw_name, body in LAYER_RE.findall(src):
        name = re.sub(r"_?layer$", "", raw_name)
        binds = parse_bindings(body)
        if not binds:
            continue
        layers.append({"id": name, "binds": binds})
    if not layers:
        raise SystemExit(f"no layers found in {path}")
    return layers


def read_layout(path: Path, count: int) -> list[dict]:
    """Read the first physical layout (key_physical_attrs, centi-units)."""
    if not path.exists():
        return []
    raw = PHYS_RE.findall(strip_comments(path.read_text()))
    keys = []
    for w, h, x, y, rot, rx, ry in raw[:count]:
        keys.append(
            {
                "w": int(w) / 100,
                "h": int(h) / 100,
                "x": int(x) / 100,
                "y": int(y) / 100,
                "rot": int(rot) / 100,
                "rx": int(rx) / 100,
                "ry": int(ry) / 100,
            }
        )
    return keys


# --------------------------------------------------------------------------
# legend vocabulary
# --------------------------------------------------------------------------

KEYTEXT = {
    "SPACE": "Space",
    "ENTER": "Enter",
    "TAB": "Tab",
    "ESC": "Esc",
    "BSPC": "Bspc",
    "DEL": "Del",
    "HOME": "Home",
    "END": "End",
    "C_PP": "Play",
    "COMMA": ",",
    "DOT": ".",
    "SLASH": "/",
    "SEMI": ";",
    "GRAVE": "`",
    "SQT": "'",
    "MINUS": "-",
    "EQUAL": "=",
    "UNDER": "_",
    "EXCL": "!",
    "AMPS": "&",
    "LBRC": "{",
    "RBRC": "}",
    "BSLH": "|",
    "PIPE": "|",
    "STAR": "*",
    "DLLR": "$",
    "LPAR": "(",
    "RPAR": ")",
    "AT": "@",
    "PRCNT": "%",
    "LBKT": "[",
    "RBKT": "]",
    "HASH": "#",
    "PLUS": "+",
    "TILDE": "~",
    "CARET": "^",
    "DQT": '"',
    "COLON": ":",
    "LEFT": "\u2190",
    "RIGHT": "\u2192",
    "UP": "\u2191",
    "DOWN": "\u2193",
}

ALIAS = {"G": "GUI", "GUI": "GUI", "A": "ALT", "ALT": "ALT",
         "C": "CTRL", "CTRL": "CTRL", "S": "SHFT", "SHFT": "SHFT"}
MODSHORT = {"GUI": "Cmd", "ALT": "Alt", "CTRL": "Ctrl", "SHFT": "Shift"}
HOLDSHORT = {"GUI": "Gui", "ALT": "Alt", "CTRL": "Ctrl", "SHFT": "Shift"}

# "symbol + space" macros carry a small "sp" suffix
MACROS = {
    "sqt_spc": ("'", "sp"),
    "grave_spc": ("`", "sp"),
    "tilde_spc": ("~", "sp"),
    "caret_spc": ("^", "sp"),
    "ae": ("\u00e4", None),
    "oe": ("\u00f6", None),
    "ue": ("\u00fc", None),
    "euro": ("\u20ac", None),
}

MORPHS = {"under_minus": "_", "bspc_del": "Bspc"}


def key_text(key: str) -> str:
    if key in KEYTEXT:
        return KEYTEXT[key]
    if re.fullmatch(r"N\d", key):
        return key[1]
    if re.fullmatch(r"F\d+", key):
        return key
    if key == "RA(S)":
        return "\u00df"  # ß
    m = re.fullmatch(r"(?:L|R)(GUI|G|ALT|A|CTRL|C|SHFT|S)\((.+)\)", key)
    if m:
        return MODSHORT[ALIAS[m.group(1)]] + key_text(m.group(2))
    if re.fullmatch(r"(?:L|R)(GUI|G|ALT|A|CTRL|C|SHFT|S)", key):
        return HOLDSHORT[ALIAS[key[1:]]]
    return key


def legend_for(bind: tuple[str, list[str]] | None):
    """Return (text, sub, small) for a binding.

    sub is ("mod", "Gui") for hold-tap mods and ("hold", layer_index) for
    layer taps; small is an optional suffix such as "sp".
    """
    if bind is None:
        return None
    name, params = bind
    if name in ("none", "trans"):
        return None
    if name == "kp":
        return key_text(params[0]), None, None
    if name in ("hml", "hmr"):
        return key_text(params[1]), ("mod", params[0][1:]), None
    if name == "lt":
        return key_text(params[1]), ("hold", int(params[0])), None
    if name == "lt_bspc_del":
        return "Bspc", ("hold", int(params[0])), None
    if name == "mo":
        return None, ("hold", int(params[0])), None
    if name in MACROS:
        text, small = MACROS[name]
        return text, None, small
    if name in MORPHS:
        return MORPHS[name], None, None
    return name, None, None


def layer_label(layer_id: str) -> str:
    return {"base": "Base", "symbol": "Sym", "umlaut": "Uml", "nav": "Nav"}.get(
        layer_id, layer_id.title()[:3] or "Lyr"
    )


# --------------------------------------------------------------------------
# geometry / palette
# --------------------------------------------------------------------------

U = 52.0          # key pitch / 1u
KW = KH = 46.0    # keycap size
M = 40.0          # canvas margin
TOP = 100.0       # y of the topmost key row
BOARD = "Architeuthis Dux"   # PCB this keymap belongs to (A. Dux)
FOOTER = 64.0     # space below the keycaps for the footer

# Fallback copy of boards/shields/arch_dux/arch_dux-layouts.dtsi (A. Dux)
# in key units, used when the devicetree layout file is not available.
_DEFAULT_POS = [
    (0, 1.33), (1, 0.31), (2, 0.00), (3, 0.28), (4, 0.42),
    (8, 0.42), (9, 0.28), (10, 0.00), (11, 0.31), (12, 1.33),
    (0, 2.33), (1, 1.31), (2, 1.00), (3, 1.28), (4, 1.42),
    (8, 1.42), (9, 1.28), (10, 1.00), (11, 1.31), (12, 2.33),
    (0, 3.33), (1, 2.31), (2, 2.00), (3, 2.28), (4, 2.42),
    (8, 2.42), (9, 2.28), (10, 2.00), (11, 2.31), (12, 3.33),
    (4, 3.75), (5, 4.00), (7, 4.00), (8, 3.75),
]


def default_layout() -> list[dict]:
    return [
        {"w": 1.0, "h": 1.0, "x": x, "y": y, "rot": 0.0, "rx": 0.0, "ry": 0.0}
        for x, y in _DEFAULT_POS
    ]


BG = "#eeeeee"
CAP_SIDE_A, CAP_SIDE_B = "#8f8f8f", "#6f6f6f"
CAP_TOP_A, CAP_TOP_B = "#d6d6d6", "#b0b0b0"
CAP_BORDER = "#3b3b3b"
CAP_EDGE = "#8a8a8a"

BASE_INK = "#1a1a1a"
SUB_INK = "#4d4d4d"
LAYER_INK = ["#1a1a1a", "#0a6b2e", "#9c0f86", "#1a3fb8"]


ARROWS = {"\u2190": 180, "\u2192": 0, "\u2191": -90, "\u2193": 90}
ARROW_RE = re.compile("([\u2190\u2191\u2192\u2193])$")


def split_arrow(text: str) -> tuple[str, str] | None:
    m = ARROW_RE.search(text)
    if not m:
        return None
    return text[: m.start()], m.group(1)


def arrow_glyph(x: float, y: float, size: float, colour: str, char: str) -> str:
    scale = size / 10.0
    return (
        f'<g transform="translate({x:.2f} {y:.2f}) rotate({ARROWS[char]}) scale({scale:.3f})">'
        f'<path d="M0.7 5 H9.2 M9.2 5 L6.1 2.1 M9.2 5 L6.1 7.9" fill="none" '
        f'stroke="{colour}" stroke-width="1.35" stroke-linecap="round" '
        f'stroke-linejoin="round"/></g>'
    )


def font_for(text: str, size: float) -> float:
    n = len(text)
    if n <= 2:
        return size
    if n == 3:
        return size - 1.5
    if n == 4:
        return size - 3.0
    if n == 5:
        return size - 4.5
    return size - 6.0


# --------------------------------------------------------------------------
# svg building blocks
# --------------------------------------------------------------------------

DEFS = f"""
<defs>
  <linearGradient id="capSide" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{CAP_SIDE_A}"/>
    <stop offset="1" stop-color="{CAP_SIDE_B}"/>
  </linearGradient>
  <linearGradient id="capTop" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{CAP_TOP_A}"/>
    <stop offset="1" stop-color="{CAP_TOP_B}"/>
  </linearGradient>
  <filter id="kshadow" x="-30%" y="-30%" width="160%" height="170%">
    <feDropShadow dx="0" dy="1.6" stdDeviation="1.5" flood-color="#000" flood-opacity="0.33"/>
  </filter>
</defs>
"""


def tspan(text, x, y, size, fill, anchor="start", weight="normal", spacing="0"):
    extra = f' letter-spacing="{spacing}"' if spacing else ""
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size:.2f}" fill="{fill}" '
        f'text-anchor="{anchor}" font-weight="{weight}"{extra}>'
        f"{escape(text)}</text>"
    )


def cap(x: float, y: float, rot: float) -> str:
    return (
        f'<g transform="translate({x:.2f} {y:.2f}) rotate({rot:.1f} {KW / 2:.2f} {KH / 2:.2f})">'
        f'<rect x="0" y="0" width="{KW}" height="{KH}" rx="5" fill="url(#capSide)" '
        f'stroke="{CAP_BORDER}" stroke-width="1" filter="url(#kshadow)"/>'
        f'<rect x="1.4" y="1.4" width="{KW - 2.8}" height="{KH - 6.2}" rx="4" '
        f'fill="url(#capTop)" stroke="{CAP_EDGE}" stroke-width="0.7"/>'
        f'<rect x="{KW / 2 - 12:.2f}" y="2.6" width="24" height="1.1" rx="0.55" '
        f'fill="#ffffff" opacity="0.35"/>'
    )


def draw_key(x: float, y: float, rot: float, binds, styles, thumb: bool = False) -> str:
    out = [cap(x, y, rot)]

    base = legend_for(binds[0] if binds else None)
    held = bool(base and base[1] and base[1][0] == "hold")

    # coloured legends in the corners: sym top-left, umlaut top-right,
    # nav bottom-right.  Thumb keys carry a hold-layer label at the bottom
    # centre, so their nav legend moves to the top-right instead.
    if held:
        slots = {1: (7.0, 14.0, "start"), 2: (KW - 7.0, 41.0, "end"),
                 3: (KW - 7.0, 14.0, "end")}
    else:
        slots = {1: (7.0, 14.0, "start"), 2: (KW - 7.0, 14.0, "end"),
                 3: (KW - 7.0, 41.0, "end")}

    for idx in (1, 2, 3):
        if idx >= len(binds) or idx >= len(styles):
            continue
        leg = legend_for(binds[idx])
        if not leg or not leg[0]:
            continue
        text, _, _ = leg
        sx, sy, anchor = slots[idx]
        size = font_for(text, 9.8 if thumb else 10.5)
        colour = styles[idx][1]
        arrow = split_arrow(text)
        if arrow:
            prefix, char = arrow
            asize = 11.0 if not thumb else 10.0
            psize = min(size, 7.8 if prefix else size)
            if anchor == "start":
                ax = sx
                if prefix:
                    out.append(tspan(prefix, sx, sy, psize, colour, "start", "600"))
                    ax = sx + 0.62 * psize * len(prefix) + 1.0
            else:
                ax = sx - asize
                if prefix:
                    out.append(tspan(prefix, ax - 1.5, sy, psize, colour, "end",
                                     "600"))
            out.append(arrow_glyph(ax, sy - 0.40 * asize, asize, colour, char))
            continue
        out.append(tspan(text, sx, sy, size, colour, anchor, "600"))
        if leg[2]:
            out.append(tspan(leg[2], sx + (7.0 if anchor == "start" else -7.0),
                             sy - 5.5, 6.0, colour, anchor, "500"))

    if base:
        text, sub, small = base
        size = font_for(text or "", 16.0)
        if text:
            out.append(tspan(text, 7.0, 32.0, size, BASE_INK, "start", "600"))
        if small:
            out.append(tspan(small, 7.0 + 8.6 * len(text), 26.0, 7.0, BASE_INK,
                             "start", "500"))
        if sub:
            kind, value = sub
            if kind == "mod":
                label, colour, weight = HOLDSHORT.get(value, value), SUB_INK, "500"
                bx, anchor = 7.0, "start"
            else:
                label, colour = (
                    styles[value] if value < len(styles) else ("Lyr", SUB_INK)
                )
                weight = "700"
                bx = KW / 2 if thumb else 7.0
                anchor = "middle" if thumb else "start"
            out.append(tspan(label, bx, 42.5, 8.8, colour, anchor, weight,
                             spacing="0.2"))

    out.append("</g>")
    return "".join(out)


# --------------------------------------------------------------------------
# page furniture
# --------------------------------------------------------------------------

def legend_chips(styles, x_right: float, y: float) -> str:
    out = []
    items = styles
    gap = 18.0
    chip = 9.0
    for label, colour in reversed(items):
        width = chip + 5 + 6.1 * len(label)
        x = x_right - width
        out.append(
            f'<rect x="{x:.2f}" y="{y - chip + 1:.2f}" width="{chip}" height="{chip}" '
            f'rx="2.4" fill="{colour}"/>'
        )
        out.append(tspan(label, x + chip + 5, y, 11.5, "#3a3a3a", "start", "600"))
        x_right = x - gap
    return "".join(out)


def build_svg(layers: list[dict], layout: list[dict], stem: str, repo: str,
              src_label: str) -> str:
    n = len(layers[0]["binds"])
    layout = layout[:n]
    styles = [
        (layer_label(lay["id"]),
         LAYER_INK[i] if i < len(LAYER_INK) else "#1a1a1a")
        for i, lay in enumerate(layers)
    ]

    min_x = min(k["x"] for k in layout)
    min_y = min(k["y"] for k in layout)
    max_x = max(k["x"] + k["w"] for k in layout)
    max_y = max(k["y"] + k["h"] for k in layout)
    canvas_w = (max_x - min_x) * U + 2 * M
    canvas_h = TOP + (max_y - min_y) * U + FOOTER

    # A. Dux is a 3x5 + 2 key column-staggered split; the trailing keys of the
    # keymap are the thumbs.
    rows, cols = 3, 5
    alpha = rows * cols * 2
    thumbs = n - alpha
    per_side = thumbs // 2

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{canvas_w:.0f}" '
        f'height="{canvas_h:.0f}" viewBox="0 0 {canvas_w:.0f} {canvas_h:.0f}" '
        f'font-family="Inter, \'Helvetica Neue\', Helvetica, Arial, \'DejaVu Sans\', sans-serif">',
        f"<title>{escape(stem)} \u2014 ZMK keymap</title>",
        "<desc>Keycap cover generated from the ZMK keymap; base, symbol, "
        "umlaut and navigation layers are colour coded.</desc>",
        DEFS,
        f'<rect width="{canvas_w:.0f}" height="{canvas_h:.0f}" fill="{BG}"/>',
    ]

    # title
    parts.append(tspan(stem, M, 46, 26, "#1a1a1a", "start", "700", spacing="0.4"))
    parts.append(tspan(f"{BOARD} \u00b7 {n} keys \u00b7 "
                       f"{rows}\u00d7{cols}+{per_side} \u00b7 "
                       f"{len(layers)} layers",
                       M, 66, 12, "#5a5a5a", "start", "500", spacing="0.3"))
    parts.append(legend_chips(styles, canvas_w - M, 46))
    parts.append(f'<rect x="{M}" y="80" width="{canvas_w - 2 * M}" height="1.2" '
                 f'fill="#d2d2d2"/>')

    # keys, placed exactly like the PCB (physical layout, 1u = U)
    for i, k in enumerate(layout):
        binds = [lay["binds"][i] for lay in layers]
        px = M + (k["x"] - min_x) * U
        py = TOP + (k["y"] - min_y) * U
        parts.append(draw_key(px, py, k["rot"], binds, styles, thumb=i >= alpha))

    # footer
    parts.append(tspan(repo, M, canvas_h - 20, 11.5, "#3a3a3a", "start", "600"))
    parts.append(tspan(f"generated from {src_label}",
                       canvas_w - M, canvas_h - 20, 10.5, "#8a8a8a", "end", "500"))
    parts.append("</svg>")
    return "\n".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("keymap", nargs="?", default="config/arch_dux.keymap")
    ap.add_argument("-l", "--layout",
                    default="boards/shields/arch_dux/arch_dux-layouts.dtsi",
                    help="physical layout devicetree (key positions)")
    ap.add_argument("-o", "--output", default="arch_dux.svg")
    args = ap.parse_args()

    path = Path(args.keymap)
    layers = read_layers(path)
    counts = {len(lay["binds"]) for lay in layers}
    if len(counts) != 1:
        raise SystemExit(f"layers have differing key counts: {counts}")
    n = counts.pop()

    layout = read_layout(Path(args.layout), n)
    if len(layout) < n:
        print(f"note: no usable physical layout in {args.layout}, "
              f"using the built-in A. Dux positions")
        layout = default_layout()

    stem = path.stem
    svg = build_svg(layers, layout, stem, "github.com/tim-hilt/zmk-config-a-dux",
                    str(path).replace("\\", "/"))
    Path(args.output).write_text(svg + "\n")
    print(f"wrote {args.output} ({len(layers)} layers, {n} keys)")


if __name__ == "__main__":
    main()
