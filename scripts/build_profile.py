#!/usr/bin/env python3
"""
Builds the animated SVG panels used by the profile README.

    pip install fonttools brotli pillow
    python3 scripts/build_profile.py

Typography (Instrument Serif, Inter, JetBrains Mono and Mrs Saint Delafield,
all SIL Open Font License) is downloaded once into scripts/.fonts, subset to
the characters each panel uses and embedded, so every panel renders the same
on every device without any external request. Project images come from media/.
"""
from __future__ import annotations

import base64
import html
import io
import math
import os
import random
import urllib.request
from pathlib import Path

from fontTools import subset as ftsubset
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
MEDIA = ROOT / "media"
FONT_DIR = Path(os.environ.get("PROFILE_FONT_DIR", ROOT / "scripts" / ".fonts"))

W = 1200
L = 64           # left content edge
R = W - 64       # right content edge

# ── palette: obsidian, ivory and champagne gold ──────────────────────────────
IVORY = "#F3EDE2"
MUTED = "#AAA397"
DIM = "#76716A"
GOLD = "#D8B77A"
GOLD_L = "#F2DFB5"
GOLD_D = "#9A7A45"
GREEN = "#93D3A2"

# ── fonts ────────────────────────────────────────────────────────────────────
GF = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
SOURCES = {
    "InstrumentSerif-Regular.ttf": GF + "instrumentserif/InstrumentSerif-Regular.ttf",
    "InstrumentSerif-Italic.ttf": GF + "instrumentserif/InstrumentSerif-Italic.ttf",
    "Inter-VF.ttf": GF + "inter/Inter%5Bopsz,wght%5D.ttf",
    "JetBrainsMono-VF.ttf": GF + "jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf",
    "MrsSaintDelafield-Regular.ttf": GF + "mrssaintdelafield/MrsSaintDelafield-Regular.ttf",
}
INSTANCES = {
    "Inter-400.ttf": ("Inter-VF.ttf", {"wght": 400, "opsz": 14}),
    "Inter-500.ttf": ("Inter-VF.ttf", {"wght": 500, "opsz": 14}),
    "Inter-600.ttf": ("Inter-VF.ttf", {"wght": 600, "opsz": 14}),
    "JBMono-400.ttf": ("JetBrainsMono-VF.ttf", {"wght": 400}),
    "JBMono-500.ttf": ("JetBrainsMono-VF.ttf", {"wght": 500}),
}

SERIF_FB = "Georgia,'Times New Roman',serif"
SANS_FB = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
MONO_FB = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"

# role -> (file, family, css fallback, style, weight)
ROLES = {
    "serif": ("InstrumentSerif-Regular.ttf", "pf-serif", SERIF_FB, "normal", 400),
    "serif-i": ("InstrumentSerif-Italic.ttf", "pf-serif-i", SERIF_FB, "italic", 400),
    "sans": ("Inter-400.ttf", "pf-sans", SANS_FB, "normal", 400),
    "sans-m": ("Inter-500.ttf", "pf-sans-m", SANS_FB, "normal", 500),
    "sans-b": ("Inter-600.ttf", "pf-sans-b", SANS_FB, "normal", 600),
    "mono": ("JBMono-400.ttf", "pf-mono", MONO_FB, "normal", 400),
    "mono-m": ("JBMono-500.ttf", "pf-mono-m", MONO_FB, "normal", 500),
    "sig": ("MrsSaintDelafield-Regular.ttf", "pf-sig", "cursive", "normal", 400),
}


def ensure_fonts() -> None:
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        target = FONT_DIR / name
        if not target.exists():
            print("downloading", name)
            urllib.request.urlretrieve(url, target)
    for name, (src, axes) in INSTANCES.items():
        target = FONT_DIR / name
        if not target.exists():
            instantiateVariableFont(TTFont(FONT_DIR / src), axes).save(target)


class Metrics:
    def __init__(self, path: Path):
        f = TTFont(path)
        self.cmap = f.getBestCmap()
        self.hmtx = f["hmtx"].metrics
        self.upm = f["head"].unitsPerEm
        self.cap = getattr(f["OS/2"], "sCapHeight", 0) or self.upm * 0.7

    def width(self, s: str, size: float, ls: float = 0) -> float:
        w = 0
        for ch in s:
            g = self.cmap.get(ord(ch))
            w += self.hmtx[g][0] if g else self.upm * 0.5
        return w * size / self.upm + ls * len(s)


_metrics: dict[str, Metrics] = {}


def M(role: str) -> Metrics:
    if role not in _metrics:
        _metrics[role] = Metrics(FONT_DIR / ROLES[role][0])
    return _metrics[role]


def tw(s: str, role: str, size: float, ls: float = 0) -> float:
    return M(role).width(s, size, ls)


def wrap(s: str, role: str, size: float, max_w: float, ls: float = 0) -> list[str]:
    lines, cur = [], ""
    for word in s.split():
        trial = f"{cur} {word}".strip()
        if cur and tw(trial, role, size, ls) > max_w:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def subset_b64(role: str, chars: set[str]) -> str:
    opts = ftsubset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["kern", "liga", "calt", "case"]
    opts.hinting = False
    opts.desubroutinize = True
    opts.name_IDs = ["*"]
    font = TTFont(FONT_DIR / ROLES[role][0])
    sub = ftsubset.Subsetter(opts)
    sub.populate(text="".join(sorted(chars)) + " ")
    sub.subset(font)
    buf = io.BytesIO()
    font.flavor = "woff2"
    font.save(buf)
    return base64.b64encode(buf.getvalue()).decode()


def esc(s: str) -> str:
    return html.escape(s, quote=True)


# ── images ───────────────────────────────────────────────────────────────────
def img_uri(path: Path, width: int | None = None, quality: int = 80) -> str:
    im = Image.open(path).convert("RGB")
    if width and im.width > width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=quality, method=6)
    return "data:image/webp;base64," + base64.b64encode(buf.getvalue()).decode()


_grain = None


def grain_uri() -> str:
    global _grain
    if _grain is None:
        rnd = random.Random(11)
        im = Image.new("LA", (128, 128))
        im.putdata([(255 if rnd.random() < 0.5 else 0, rnd.randint(0, 22)) for _ in range(128 * 128)])
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True)
        _grain = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return _grain


# ── document ─────────────────────────────────────────────────────────────────
class Doc:
    def __init__(self, w: int, h: int, title: str, desc: str):
        self.w, self.h, self.title, self.desc = w, h, title, desc
        self.defs: list[str] = []
        self.body: list[str] = []
        self.css: list[str] = []
        self.used: dict[str, set[str]] = {}

    def use(self, role: str, txt: str) -> None:
        self.used.setdefault(role, set()).update(txt)

    def add(self, *parts: str) -> None:
        self.body.extend(parts)

    def text(self, x, y, size, segs, anchor="start", ls=0, extra="", cls="") -> str:
        """segs: list of (text, role, fill). Returns a <text> element."""
        if isinstance(segs, tuple):
            segs = [segs]
        attrs = f'x="{x:.1f}" y="{y:.1f}" font-size="{size}"'
        if anchor != "start":
            attrs += f' text-anchor="{anchor}"'
        if ls:
            attrs += f' letter-spacing="{ls}"'
        if extra:
            attrs += " " + extra
        if len(segs) == 1:
            txt, role, fill = segs[0]
            self.use(role, txt)
            return f'<text {attrs} class="{(role + " " + cls).strip()}" fill="{fill}">{esc(txt)}</text>'
        spans = []
        for txt, role, fill in segs:
            self.use(role, txt)
            spans.append(f'<tspan class="{role}" fill="{fill}">{esc(txt)}</tspan>')
        klass = f' class="{cls}"' if cls else ""
        return f"<text {attrs}{klass}>{''.join(spans)}</text>"

    def t(self, *a, **k) -> None:
        self.add(self.text(*a, **k))

    def svg(self) -> str:
        css = []
        for role, chars in sorted(self.used.items()):
            _, fam, fb, style, weight = ROLES[role]
            css.append(
                f"@font-face{{font-family:'{fam}';src:url(data:font/woff2;base64,{subset_b64(role, chars)}) "
                f"format('woff2');font-style:{style};font-weight:{weight};}}"
            )
            css.append(f".{role}{{font-family:'{fam}',{fb};font-style:{style};font-weight:{weight};}}")
        css += self.css
        css.append("@media (prefers-reduced-motion:reduce){*{animation:none!important;}}")
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" width="{self.w}" '
            f'height="{self.h}" role="img" aria-labelledby="t d">\n'
            f'<title id="t">{esc(self.title)}</title>\n<desc id="d">{esc(self.desc)}</desc>\n'
            f"<defs>\n{chr(10).join(self.defs)}\n</defs>\n"
            f"<style><![CDATA[\n{chr(10).join(css)}\n]]></style>\n"
            f"{chr(10).join(self.body)}\n</svg>\n"
        )

    def save(self, name: str) -> None:
        out = ASSETS / name
        data = self.svg()
        out.write_text(data, encoding="utf-8")
        print(f"{name:32s} {len(data) / 1024:7.1f} KB")


# ── shared building blocks ───────────────────────────────────────────────────
def card(d: Doc, glows=(), rx=26) -> None:
    """Background card: obsidian gradient, soft light, film grain, hairline edge."""
    w, h = d.w, d.h
    d.defs += [
        f'<clipPath id="card"><rect width="{w}" height="{h}" rx="{rx}"/></clipPath>',
        '<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#141311"/><stop offset="1" stop-color="#0A0A0A"/></linearGradient>',
        f'<linearGradient id="edge" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="{w}" y2="{h}">'
        f'<stop offset="0" stop-color="{GOLD}" stop-opacity=".55"/>'
        f'<stop offset=".35" stop-color="{IVORY}" stop-opacity=".10"/>'
        f'<stop offset=".7" stop-color="{IVORY}" stop-opacity=".06"/>'
        f'<stop offset="1" stop-color="{GOLD}" stop-opacity=".30"/></linearGradient>',
        f'<pattern id="grain" width="128" height="128" patternUnits="userSpaceOnUse">'
        f'<image href="{grain_uri()}" width="128" height="128"/></pattern>',
    ]
    d.add('<g clip-path="url(#card)">', f'<rect width="{w}" height="{h}" fill="url(#bg)"/>')
    for i, (cx, cy, r, color, op, cls) in enumerate(glows):
        d.defs.append(
            f'<radialGradient id="glow{i}"><stop offset="0" stop-color="{color}" stop-opacity="{op}"/>'
            f'<stop offset=".45" stop-color="{color}" stop-opacity="{op * 0.35:.3f}"/>'
            f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></radialGradient>'
        )
        cl = f' class="{cls}"' if cls else ""
        d.add(f'<circle{cl} cx="{cx}" cy="{cy}" r="{r}" fill="url(#glow{i})"/>')
    d.body.append("<!--content-->")


def close_card(d: Doc, rx=26) -> None:
    w, h = d.w, d.h
    d.add(f'<rect width="{w}" height="{h}" fill="url(#grain)" opacity=".7" pointer-events="none"/>', "</g>")
    d.add(f'<rect x=".75" y=".75" width="{w - 1.5}" height="{h - 1.5}" rx="{rx - .75}" fill="none" '
          f'stroke="url(#edge)" stroke-width="1.5"/>')


def section_head(d: Doc, num: str, label: str, right: str, y: int = 66) -> None:
    x = L
    d.t(x, y, 14, (num, "mono-m", GOLD), ls=2)
    x += tw(num, "mono-m", 14, 2) + 14
    d.t(x, y, 14, (label, "mono", IVORY), ls=3.2)
    x += tw(label, "mono", 14, 3.2) + 22
    rw = tw(right, "mono", 13, 2.6)
    d.add(f'<line x1="{x:.1f}" y1="{y - 5}" x2="{R - rw - 22:.1f}" y2="{y - 5}" stroke="{GOLD}" '
          f'stroke-opacity=".22"/>')
    d.t(R, y, 13, (right, "mono", DIM), anchor="end", ls=2.6)


def diamond(x, y, s=4.5, fill=GOLD, op=1.0, extra="") -> str:
    return (f'<path d="M{x} {y - s}L{x + s} {y}L{x} {y + s}L{x - s} {y}Z" fill="{fill}" '
            f'fill-opacity="{op}" {extra}/>')


def sheen_defs(d: Doc) -> None:
    d.defs.append(
        '<linearGradient id="sheenG" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="{IVORY}" stop-opacity="0"/>'
        '<stop offset=".5" stop-color="#FFFFFF" stop-opacity=".85"/>'
        f'<stop offset="1" stop-color="{IVORY}" stop-opacity="0"/></linearGradient>'
    )


def gold_text_grad(d: Doc, gid: str, x1: float, x2: float) -> None:
    d.defs.append(
        f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="{x1}" y1="0" x2="{x2}" y2="0">'
        f'<stop offset="0" stop-color="{GOLD_L}"/><stop offset=".55" stop-color="{GOLD}"/>'
        f'<stop offset="1" stop-color="{GOLD_D}"/></linearGradient>'
    )


def sheen_over(d: Doc, cid: str, text_el: str, x: float, y_top: float, h: float, travel: float,
               dur: float = 8, delay: float = 2) -> None:
    """Moving light band clipped to a text shape (CSS-only, respects reduced motion)."""
    d.defs.append(f'<clipPath id="{cid}">{text_el}</clipPath>')
    d.add(f'<g clip-path="url(#{cid})"><g class="sh-{cid}"><rect x="{x - 220:.0f}" y="{y_top:.0f}" '
          f'width="150" height="{h:.0f}" fill="url(#sheenG)" transform="skewX(-18)"/></g></g>')
    d.css.append(
        f".sh-{cid}{{animation:sh-{cid} {dur}s cubic-bezier(.6,0,.25,1) {delay}s infinite;}}"
        f"@keyframes sh-{cid}{{0%{{transform:translateX(0)}}40%,100%{{transform:translateX({travel:.0f}px)}}}}"
    )


# ── panels ───────────────────────────────────────────────────────────────────
def hero() -> None:
    d = Doc(W, 640, "Suhail Chalil — Freelance developer and creative technologist",
            "Digital experiences with strong design and practical engineering. Web development, mobile apps, "
            "AI automation, AI video and digital marketing. Open to freelance work.")
    card(d, glows=[(950, 270, 470, GOLD, .30, "drift"), (90, 660, 380, "#B8875A", .18, "")])
    sheen_defs(d)
    d.css += [
        ".drift{animation:drift 18s ease-in-out infinite alternate;}"
        "@keyframes drift{from{transform:translate(0,0)}to{transform:translate(-60px,30px)}}",
        ".spin{transform-box:view-box;transform-origin:935px 300px;animation:spin 48s linear infinite;}"
        ".spin-r{transform-box:view-box;transform-origin:935px 300px;animation:spin 90s linear infinite reverse;}"
        ".orbit{transform-box:view-box;transform-origin:935px 300px;animation:spin 14s linear infinite;}"
        "@keyframes spin{to{transform:rotate(360deg)}}",
        ".pulse{transform-box:fill-box;transform-origin:center;animation:pulse 2.4s ease-out infinite;}"
        "@keyframes pulse{0%{transform:scale(.6);opacity:.9}100%{transform:scale(2.6);opacity:0}}",
    ]
    # editorial column hairlines
    for x in range(100, 1200, 100):
        d.add(f'<line x1="{x}" y1="0" x2="{x}" y2="640" stroke="{IVORY}" stroke-opacity=".028"/>')

    # top bar
    d.add(diamond(L + 4, 60, 4))
    d.t(L + 18, 65, 13, ("PORTFOLIO — 2026", "mono", MUTED), ls=3)
    d.t(560, 65, 13, ("ABOUT · WORK · APPROACH · TOOLKIT · CONTACT", "mono", DIM), anchor="middle", ls=3)
    label = "OPEN TO FREELANCE WORK"
    pw = tw(label, "mono-m", 12, 2.4) + 54
    px = R - pw
    d.add(f'<rect x="{px:.1f}" y="42" width="{pw:.1f}" height="36" rx="18" fill="{GOLD}" fill-opacity=".07" '
          f'stroke="{GOLD}" stroke-opacity=".38"/>')
    d.add(f'<circle class="pulse" cx="{px + 22:.1f}" cy="60" r="4" fill="{GREEN}"/>')
    d.add(f'<circle cx="{px + 22:.1f}" cy="60" r="4" fill="{GREEN}"/>')
    d.t(px + 36, 64.5, 12, (label, "mono-m", IVORY), ls=2.4)
    d.add(f'<line x1="{L}" y1="102" x2="{R}" y2="102" stroke="{IVORY}" stroke-opacity=".09"/>')

    # eyebrow
    d.add(f'<line x1="{L}" y1="190" x2="{L + 40}" y2="190" stroke="{GOLD}"/>')
    d.t(L + 56, 195, 14, ("FREELANCE DEVELOPER  ·  CREATIVE TECHNOLOGIST", "mono", GOLD), ls=4)

    # name
    gold_text_grad(d, "nameG", 140, 560)
    d.t(56, 336, 156, ("Suhail", "serif", IVORY), ls=-3)
    chalil = d.text(140, 466, 156, ("Chalil.", "serif-i", "url(#nameG)"), ls=-3)
    d.add(chalil)
    sheen_over(d, "nm", chalil, 140, 330, 160, 760, dur=8, delay=1.5)

    # tagline + bottom strip
    d.t(L, 534, 22, ("Digital experiences with strong design and practical engineering.", "sans", MUTED))
    d.add(f'<line x1="{L}" y1="576" x2="{R}" y2="576" stroke="{IVORY}" stroke-opacity=".09"/>')
    d.t(L, 606, 12.5, ("WEB DEVELOPMENT · MOBILE APPS · AI AUTOMATION · AI VIDEO · DIGITAL MARKETING",
                       "mono", DIM), ls=2.4)
    d.t(R, 606, 12.5, ("SELECTED WORK ↓", "mono-m", GOLD), anchor="end", ls=2.4)

    # emblem
    cx, cy = 935, 300
    d.defs += [
        f'<radialGradient id="disc" cx="40%" cy="35%" r="75%"><stop offset="0" stop-color="#1D1913"/>'
        f'<stop offset="1" stop-color="#0B0A09"/></radialGradient>',
        f'<path id="ring" d="M{cx - 140} {cy} a140 140 0 1 1 280 0 a140 140 0 1 1 -280 0"/>',
    ]
    d.add(f'<circle cx="{cx}" cy="{cy}" r="196" fill="none" stroke="{GOLD}" stroke-opacity=".10"/>')
    d.add(f'<g class="spin-r"><circle cx="{cx}" cy="{cy}" r="178" fill="none" stroke="{GOLD}" '
          f'stroke-opacity=".35" stroke-dasharray="1 7"/></g>')
    for a in range(0, 360, 90):
        rad = math.radians(a)
        d.add(diamond(cx + 178 * math.cos(rad), cy + 178 * math.sin(rad), 4, GOLD, .9))
    d.add(f'<g class="orbit"><circle cx="{cx + 196}" cy="{cy}" r="3.5" fill="{GOLD_L}"/>'
          f'<circle cx="{cx + 196}" cy="{cy}" r="9" fill="{GOLD}" fill-opacity=".18"/></g>')
    ring_txt = "DESIGN · DEVELOPMENT · GROWTH · " * 2
    base = tw(ring_txt, "mono-m", 15)
    ls = (2 * math.pi * 140 - base) / len(ring_txt)
    d.use("mono-m", ring_txt)
    d.add(f'<g class="spin"><text font-size="15" class="mono-m" fill="{GOLD_L}" fill-opacity=".85" '
          f'letter-spacing="{ls:.3f}"><textPath href="#ring">{esc(ring_txt)}</textPath></text></g>')
    d.add(f'<circle cx="{cx}" cy="{cy}" r="116" fill="url(#disc)" stroke="{GOLD}" stroke-opacity=".45"/>')
    d.add(f'<circle cx="{cx}" cy="{cy}" r="106" fill="none" stroke="{GOLD}" stroke-opacity=".15"/>')
    gold_text_grad(d, "monoG", cx - 70, cx + 70)
    mono = d.text(cx - 2, cy + 34, 104, [("S", "serif", "url(#monoG)"), ("c", "serif-i", "url(#monoG)")],
                  anchor="middle", ls=-2)
    d.add(mono)
    sheen_over(d, "mg", mono, cx - 80, cy - 70, 140, 400, dur=8, delay=4.5)
    d.add(diamond(cx, cy + 62, 3.5, GOLD, .7))

    close_card(d)
    d.save("hero.svg")


def about() -> None:
    d = Doc(W, 600, "About — Strong design, practical engineering, real results.",
            "I’m a freelance developer and creative technologist. I build websites and mobile experiences, use AI "
            "to automate useful work and make video, and connect the finished product to digital marketing. "
            "Services: web development, mobile apps, AI automation, AI video, digital marketing.")
    card(d, glows=[(1150, 40, 420, GOLD, .16, "")])
    section_head(d, "01", "ABOUT", "WHO I AM")

    gold_text_grad(d, "hG", L, 520)
    d.t(L - 2, 168, 60, ("Strong design,", "serif", IVORY), ls=-1)
    d.t(L - 2, 234, 60, ("practical engineering,", "serif", IVORY), ls=-1)
    d.t(L - 2, 300, 60, ("real results.", "serif-i", "url(#hG)"), ls=-1)

    body = ("I’m a freelance developer and creative technologist. I build websites and mobile experiences, "
            "use AI to automate useful work and make video, and connect the finished product to digital marketing.")
    for i, line in enumerate(wrap(body, "sans", 18.5, 540)):
        d.t(L, 372 + i * 31, 18.5, (line, "sans", MUTED))
    d.add(f'<line x1="{L}" y1="512" x2="{L + 540}" y2="512" stroke="{IVORY}" stroke-opacity=".09"/>')
    d.add(f'<circle class="pulse" cx="{L + 5}" cy="542" r="4" fill="{GREEN}"/><circle cx="{L + 5}" cy="542" r="4" '
          f'fill="{GREEN}"/>')
    d.t(L + 22, 546.5, 12.5, ("CURRENTLY TAKING ON SELECT FREELANCE PROJECTS", "mono", MUTED), ls=2.2)

    # services index
    x0, y0, rh = 690, 128, 82
    items = [
        ("Web development", "Sites, storefronts and full-stack products"),
        ("Mobile apps", "Mobile-first interfaces and experiences"),
        ("AI automation", "Automating the useful, repetitive work"),
        ("AI video", "Generated video and motion content"),
        ("Digital marketing", "Connecting the product to growth"),
    ]
    d.t(x0, 112, 12.5, ("WHAT I DO", "mono-m", GOLD), ls=3)
    d.t(R, 112, 12.5, ("05 SERVICES", "mono", DIM), anchor="end", ls=3)
    # moving spotlight
    n = len(items)
    frames = []
    for i in range(n):
        a, b = i * 100 / n, (i + 0.82) * 100 / n
        frames.append(f"{a:.1f}%,{b:.1f}%{{transform:translateY({i * rh}px)}}")
    frames.append(f"100%{{transform:translateY(0px)}}")
    d.css.append(".spot{animation:spot 12.5s cubic-bezier(.7,0,.3,1) infinite;}@keyframes spot{"
                 + "".join(frames) + "}")
    d.defs.append(f'<linearGradient id="spotG" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{GOLD}" '
                  f'stop-opacity=".16"/><stop offset="1" stop-color="{GOLD}" stop-opacity="0"/></linearGradient>')
    d.add(f'<g class="spot"><rect x="{x0}" y="{y0 + 1}" width="{R - x0}" height="{rh - 1}" fill="url(#spotG)"/>'
          f'<rect x="{x0}" y="{y0 + 1}" width="2" height="{rh - 1}" fill="{GOLD}"/></g>')
    for i, (title, sub) in enumerate(items):
        y = y0 + i * rh
        d.add(f'<line x1="{x0}" y1="{y}" x2="{R}" y2="{y}" stroke="{IVORY}" stroke-opacity=".10"/>')
        d.t(x0 + 20, y + 46, 13, (f"0{i + 1}", "mono-m", GOLD), ls=1)
        d.t(x0 + 64, y + 44, 34, (title, "serif", IVORY), ls=-.3)
        d.t(x0 + 64, y + 66, 14, (sub, "sans", DIM))
        d.t(R - 4, y + 46, 18, ("↗", "sans", MUTED), anchor="end")
    d.add(f'<line x1="{x0}" y1="{y0 + n * rh}" x2="{R}" y2="{y0 + n * rh}" stroke="{IVORY}" stroke-opacity=".10"/>')

    close_card(d)
    d.save("about.svg")


def phone(d: Doc, pid: str, cx: float, cy: float, w: float, uri: str, rot: float, cls: str) -> None:
    h = w * 1349 / 620
    x, y = cx - w / 2, cy - h / 2
    b = 7
    d.defs.append(f'<clipPath id="scr{pid}"><rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
                  f'rx="{w * .12:.1f}"/></clipPath>')
    d.add(f'<g class="{cls}"><g transform="rotate({rot} {cx:.1f} {cy + h / 2:.1f})">')
    d.add(f'<ellipse cx="{cx:.1f}" cy="{y + h + 26:.1f}" rx="{w * .55:.1f}" ry="12" fill="url(#shadow)"/>')
    d.add(f'<rect x="{x - b:.1f}" y="{y - b:.1f}" width="{w + 2 * b:.1f}" height="{h + 2 * b:.1f}" '
          f'rx="{w * .12 + b:.1f}" fill="#0D0D0E" stroke="{GOLD}" stroke-opacity=".38"/>')
    d.add(f'<image href="{uri}" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
          f'preserveAspectRatio="xMidYMid slice" clip-path="url(#scr{pid})"/>')
    d.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{w * .12:.1f}" '
          f'fill="url(#glass)"/>')
    d.add(f'<rect x="{cx - w * .14:.1f}" y="{y + 9:.1f}" width="{w * .28:.1f}" height="{w * .065:.1f}" '
          f'rx="{w * .0325:.1f}" fill="#050505"/>')
    d.add("</g></g>")


def invito() -> None:
    d = Doc(W, 780, "Invito Bello — a premium digital-invitation product",
            "Featured project. A premium digital-invitation product designed and developed from scratch: "
            "13 original mobile-first designs, a live personalisation studio, secure publishing after payment, "
            "RSVP and guest replies. Role: product, design, frontend, backend and motion. Stack: Next.js, React, "
            "TypeScript, GSAP, Three.js, Supabase, Stripe, Razorpay, Resend.")
    card(d, glows=[(880, 400, 460, GOLD, .26, ""), (60, 80, 300, GOLD, .08, "")])
    section_head(d, "02", "SELECTED WORK", "N° 01 — FEATURED PRODUCT")

    # left column
    d.t(L, 168, 13, ("FULL-STACK PRODUCT  ·  PRE-LAUNCH", "mono-m", GOLD), ls=3)
    gold_text_grad(d, "tG", 300, 560)
    title = d.text(L - 3, 262, 96, [("Invito ", "serif", IVORY), ("Bello.", "serif-i", "url(#tG)")], ls=-2)
    d.add(title)
    sheen_defs(d)
    sheen_over(d, "ti", title, L, 180, 110, 760, dur=9, delay=2)
    sub = "A premium digital-invitation product, designed and developed from scratch."
    for i, line in enumerate(wrap(sub, "sans-m", 20, 470)):
        d.t(L, 314 + i * 30, 20, (line, "sans-m", IVORY))
    body = ("Couples choose a design, personalise it in a live editor, publish securely after payment and share "
            "one elegant link with every guest.")
    for i, line in enumerate(wrap(body, "sans", 16.5, 470)):
        d.t(L, 388 + i * 27, 16.5, (line, "sans", MUTED))

    stats = [("13", "ORIGINAL", "DESIGNS"), ("Live", "PERSONALISATION", "STUDIO"), ("RSVP", "GUEST REPLIES", "& TRACKING")]
    for i, (v, a, b) in enumerate(stats):
        x = L + i * 166
        d.add(f'<line x1="{x}" y1="486" x2="{x + 140}" y2="486" stroke="{GOLD}" stroke-opacity=".35"/>')
        d.t(x, 546, 52, (v, "serif", GOLD_L), ls=-1)
        d.t(x, 574, 11, (a, "mono", DIM), ls=1.8)
        d.t(x, 591, 11, (b, "mono", DIM), ls=1.8)

    # phones
    d.defs += [
        '<radialGradient id="shadow"><stop offset="0" stop-color="#000" stop-opacity=".7"/>'
        '<stop offset="1" stop-color="#000" stop-opacity="0"/></radialGradient>',
        '<linearGradient id="glass" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff" '
        'stop-opacity=".16"/><stop offset=".35" stop-color="#fff" stop-opacity="0"/></linearGradient>',
    ]
    d.css.append(
        ".f1,.f2,.f3,.f4,.f5{animation:float 7s ease-in-out infinite;}"
        ".f2{animation-delay:-1.4s}.f3{animation-delay:-2.8s}.f4{animation-delay:-4.2s}.f5{animation-delay:-5.6s}"
        "@keyframes float{0%,100%{transform:translateY(0)}50%{transform:translateY(-10px)}}"
    )
    # arch motif behind the phones
    d.add(f'<path d="M672 690V330a200 200 0 0 1 400 0V690" fill="none" stroke="{GOLD}" stroke-opacity=".16"/>')
    d.add(f'<path d="M692 690V330a180 180 0 0 1 360 0V690" fill="none" stroke="{GOLD}" stroke-opacity=".08"/>')
    covers = MEDIA / "invito-bello"
    c = 872
    phone(d, "a", c - 214, 404, 124, img_uri(covers / "opaline-tide.webp", 260), -9, "f1")
    phone(d, "e", c + 214, 404, 124, img_uri(covers / "pearl-vow.webp", 260), 9, "f5")
    phone(d, "b", c - 118, 396, 158, img_uri(covers / "olive-atelier.webp", 320), -4.5, "f2")
    phone(d, "d", c + 118, 396, 158, img_uri(covers / "rouge-majlis.webp", 320), 4.5, "f4")
    phone(d, "c", c, 388, 196, img_uri(covers / "editorial-noir.webp", 400), 0, "f3")
    d.t(c, 676, 11.5, ("FIVE OF THIRTEEN ORIGINAL DESIGNS", "mono", DIM), anchor="middle", ls=2.6)

    # bottom strip
    d.add(f'<line x1="{L}" y1="708" x2="{R}" y2="708" stroke="{IVORY}" stroke-opacity=".09"/>')
    d.t(L, 744, 12, ("ROLE", "mono-m", GOLD), ls=2.4)
    d.t(L + 62, 744, 15, ("Product · Design · Frontend · Backend · Motion", "sans", IVORY))
    stack = "Next.js · React · TypeScript · GSAP · Three.js · Supabase · Stripe"
    sw = tw(stack, "sans", 15)
    d.t(R - sw - 18, 744, 12, ("STACK", "mono-m", GOLD), anchor="end", ls=2.4)
    d.t(R, 744, 15, (stack, "sans", IVORY), anchor="end")

    close_card(d)
    d.save("work-invito-bello.svg")


def project(file: str, num: str, kind: str, url: str, t1: str, t2: str, desc: str, feats: list[str],
            stack: str, image: Path, accent: str, flip: bool) -> None:
    d = Doc(W, 560, f"{t1} {t2.rstrip('.')} — {kind.title()}",
            f"{desc} Highlights: {', '.join(feats)}. Built with {stack}. Live demo at {url}.")
    fw = 620
    ih = fw * 9 / 16
    fy = 118
    fx = R - fw if flip else L
    tx = L if flip else fx + fw + 56
    tcol = (fx - 56 - L) if flip else (R - tx)
    card(d, glows=[(fx + fw / 2, fy + 210, 420, accent, .34, ""), (tx + 200, 500, 300, GOLD, .10, "")])
    section_head(d, num, kind, url.replace("https://", "").rstrip("/").upper())

    # browser frame
    d.defs.append(f'<clipPath id="shot"><path d="M{fx} {fy + 38}H{fx + fw}V{fy + 38 + ih - 14:.1f}'
                  f'a14 14 0 0 1 -14 14H{fx + 14}a14 14 0 0 1 -14 -14Z"/></clipPath>')
    d.add(f'<rect x="{fx - 1}" y="{fy - 1}" width="{fw + 2}" height="{ih + 40:.1f}" rx="15" fill="#0E0E0F" '
          f'stroke="{IVORY}" stroke-opacity=".14"/>')
    for i in range(3):
        d.add(f'<circle cx="{fx + 22 + i * 17}" cy="{fy + 19}" r="5" fill="{IVORY}" fill-opacity=".16"/>')
    host = url.replace("https://", "").rstrip("/")
    uw = tw(host, "mono", 11.5, .4) + 40
    d.add(f'<rect x="{fx + fw / 2 - uw / 2:.1f}" y="{fy + 7}" width="{uw:.1f}" height="24" rx="12" fill="{IVORY}" '
          f'fill-opacity=".05"/>')
    d.t(fx + fw / 2, fy + 23.5, 11.5, (host, "mono", MUTED), anchor="middle", ls=.4)
    d.css.append(f".kb{{transform-box:view-box;transform-origin:{fx + fw / 2}px {fy + 38 + ih / 2:.1f}px;"
                 "animation:kb 22s ease-in-out infinite alternate;}"
                 "@keyframes kb{from{transform:scale(1)}to{transform:scale(1.06)}}")
    d.add(f'<g clip-path="url(#shot)"><image class="kb" href="{img_uri(image, 960, 82)}" x="{fx}" y="{fy + 38}" '
          f'width="{fw}" height="{ih:.1f}" preserveAspectRatio="xMidYMid slice"/></g>')

    # text column
    gold_text_grad(d, "tG", tx, tx + 360)
    d.t(tx - 2, 196, 68, (t1, "serif", IVORY), ls=-1.2)
    d.t(tx - 2, 262, 68, (t2, "serif-i", "url(#tG)"), ls=-1.2)
    y = 312
    for line in wrap(desc, "sans", 16.5, tcol):
        d.t(tx, y, 16.5, (line, "sans", MUTED))
        y += 25
    y += 15
    for f in feats:
        d.add(diamond(tx + 5, y - 5, 4.2))
        d.t(tx + 22, y, 15, (f, "sans", IVORY))
        y += 26
    base = fy + 38 + ih
    d.add(f'<line x1="{tx}" y1="{base - 32:.1f}" x2="{tx + tcol}" y2="{base - 32:.1f}" stroke="{IVORY}" '
          f'stroke-opacity=".10"/>')
    d.t(tx, base - 2, 12, (stack.upper(), "mono", MUTED), ls=2)
    d.t(tx + tcol, base - 2, 12, ("LIVE ↗", "mono-m", GOLD), anchor="end", ls=2.4)

    close_card(d)
    d.save(file)


def approach() -> None:
    d = Doc(W, 480, "Approach — the details people feel",
            "Clear hierarchy, mobile behaviour, fast loading, thoughtful motion and a reliable path from an idea "
            "to a usable product.")
    card(d, glows=[(90, 40, 380, GOLD, .14, "")])
    section_head(d, "03", "APPROACH", "HOW I WORK")
    gold_text_grad(d, "hG", 560, 760)
    d.t(L - 2, 170, 62, [("The details people ", "serif", IVORY), ("feel.", "serif-i", "url(#hG)")], ls=-1)
    d.t(L, 214, 18, ("I care about what makes a product feel finished — on every screen, at every step.",
                     "sans", MUTED))

    steps = [
        ("Clear hierarchy", "Every screen reads at a glance."),
        ("Mobile behaviour", "Designed for the phone first."),
        ("Fast loading", "Performance is part of the design."),
        ("Thoughtful motion", "Animation that guides, not decorates."),
        ("Idea to product", "A reliable path to something usable."),
    ]
    ly = 290
    col = (R - L) / len(steps)
    d.add(f'<line x1="{L}" y1="{ly}" x2="{R}" y2="{ly}" stroke="{GOLD}" stroke-opacity=".25"/>')
    d.defs.append(f'<linearGradient id="trail" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{GOLD}" '
                  f'stop-opacity="0"/><stop offset="1" stop-color="{GOLD_L}"/></linearGradient>')
    dur = 7.5
    d.css.append(f".run{{animation:run {dur}s cubic-bezier(.45,0,.55,1) infinite;}}"
                 f"@keyframes run{{0%{{transform:translateX(0);opacity:0}}6%{{opacity:1}}88%{{opacity:1}}"
                 f"100%{{transform:translateX({R - L}px);opacity:0}}}}")
    for i, (title, sub) in enumerate(steps):
        x = L + i * col
        frac = (i * col) / (R - L)
        a = max(frac * 100 * 0.94, 0.1)
        d.css.append(
            f".n{i}{{animation:n{i} {dur}s linear infinite;}}"
            f"@keyframes n{i}{{0%,{max(a - .1, 0):.1f}%{{fill:#0B0B0B}}{a + .5:.1f}%{{fill:{GOLD_L}}}"
            f"{min(a + 14, 99):.1f}%,100%{{fill:#0B0B0B}}}}"
        )
        d.t(x, ly - 20, 12.5, (f"0{i + 1}", "mono-m", GOLD), ls=1.5)
        d.add(f'<circle class="n{i}" cx="{x + 6}" cy="{ly}" r="6" fill="#0B0B0B" stroke="{GOLD}" '
              f'stroke-width="1.5"/>')
        d.t(x, ly + 60, 30, (title, "serif", IVORY), ls=-.3)
        for j, line in enumerate(wrap(sub, "sans", 15.5, col - 30)):
            d.t(x, ly + 90 + j * 24, 15.5, (line, "sans", MUTED))
    d.add(f'<g class="run"><rect x="{L - 90}" y="{ly - 1}" width="90" height="2" fill="url(#trail)"/>'
          f'<circle cx="{L}" cy="{ly}" r="3" fill="{GOLD_L}"/><circle cx="{L}" cy="{ly}" r="10" fill="{GOLD}" '
          f'fill-opacity=".18"/></g>')

    close_card(d)
    d.save("approach.svg")


def toolkit() -> None:
    tools = [
        ("Nx", "Next.js", "FRAMEWORK"), ("Re", "React", "INTERFACE"), ("Ts", "TypeScript", "LANGUAGE"),
        ("Cs", "CSS", "STYLING"), ("Gs", "GSAP", "MOTION"), ("Th", "Three.js", "3D · WEBGL"),
        ("Sb", "Supabase", "BACKEND"), ("Gt", "Git", "WORKFLOW"),
    ]
    d = Doc(W, 620, "Toolkit — a focused, modern stack",
            "Core tools: " + ", ".join(t[1] for t in tools) + ". Also shipped with Razorpay, Stripe, Resend and WebGL.")
    card(d, glows=[(1100, 600, 420, GOLD, .14, "")])
    section_head(d, "04", "TOOLKIT", "CORE STACK")
    gold_text_grad(d, "hG", 470, 640)
    d.t(L - 2, 170, 62, [("A focused, modern ", "serif", IVORY), ("stack.", "serif-i", "url(#hG)")], ls=-1)

    cols, gap, th = 4, 16, 150
    tw_ = (R - L - gap * (cols - 1)) / cols
    cycle = 9.6
    d.defs.append(f'<linearGradient id="sym" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{GOLD_L}"/>'
                  f'<stop offset="1" stop-color="{GOLD}"/></linearGradient>')
    for i, (sym, name, cat) in enumerate(tools):
        x = L + (i % cols) * (tw_ + gap)
        y = 218 + (i // cols) * (th + gap)
        d.add(f'<rect x="{x:.1f}" y="{y}" width="{tw_:.1f}" height="{th}" rx="16" fill="{IVORY}" '
              f'fill-opacity=".025" stroke="{IVORY}" stroke-opacity=".09"/>')
        delay = i * cycle / len(tools)
        d.add(f'<rect class="hl" style="animation-delay:{delay:.2f}s" x="{x:.1f}" y="{y}" width="{tw_:.1f}" '
              f'height="{th}" rx="16" fill="{GOLD}" fill-opacity=".05" stroke="{GOLD}" stroke-opacity=".7"/>')
        d.t(x + 22, y + 34, 12, (f"{i + 1:02d}", "mono-m", GOLD), ls=1.5)
        d.t(x + tw_ - 22, y + 34, 11, (cat, "mono", DIM), anchor="end", ls=2)
        d.t(x + 20, y + 106, 64, (sym, "serif", "url(#sym)"), ls=-1)
        d.t(x + tw_ - 22, y + 126, 17, (name, "sans-m", IVORY), anchor="end")
    d.css.append(f".hl{{opacity:0;animation:hl {cycle}s ease-in-out infinite;}}"
                 f"@keyframes hl{{0%{{opacity:0}}5%{{opacity:1}}14%{{opacity:1}}24%,100%{{opacity:0}}}}")
    d.add(f'<line x1="{L}" y1="560" x2="{R}" y2="560" stroke="{IVORY}" stroke-opacity=".09"/>')
    d.t(L, 592, 12, ("ALSO SHIPPED WITH", "mono-m", GOLD), ls=2.4)
    d.t(L + 186, 592, 15, ("Razorpay · Stripe · Resend · WebGL", "sans", IVORY))
    d.t(R, 592, 12, ("PERFORMANCE · ACCESSIBILITY · MOTION", "mono", DIM), anchor="end", ls=2.4)
    close_card(d)
    d.save("toolkit.svg")


def contact() -> None:
    d = Doc(W, 620, "Work with me — Have something worth building?",
            "I’m available for freelance websites, mobile app interfaces, AI automation, AI video and digital "
            "marketing projects. — Suhail Chalil")
    card(d, glows=[(960, 300, 470, GOLD, .22, "drift"), (80, 620, 320, GOLD, .10, "")])
    sheen_defs(d)
    d.css.append(".drift{animation:drift 18s ease-in-out infinite alternate;}"
                 "@keyframes drift{from{transform:translate(0,0)}to{transform:translate(-50px,24px)}}")
    section_head(d, "05", "WORK WITH ME", "AVAILABILITY — OPEN")

    d.t(L - 3, 224, 100, ("Have something", "serif", IVORY), ls=-2.5)
    gold_text_grad(d, "hG", L, 640)
    worth = d.text(L - 3, 318, 100, ("worth building?", "serif-i", "url(#hG)"), ls=-2.5)
    d.add(worth)
    sheen_over(d, "wb", worth, L, 230, 110, 900, dur=9, delay=3)
    body = ("I’m available for freelance websites, mobile app interfaces, AI automation, AI video and digital "
            "marketing projects.")
    for i, line in enumerate(wrap(body, "sans", 19, 560)):
        d.t(L, 380 + i * 31, 19, (line, "sans", MUTED))

    # signature, drawn like handwriting, then filled
    sx, sy = R, 300
    d.css.append(".pen{stroke-dasharray:1600;stroke-dashoffset:0;animation:pen 4.2s cubic-bezier(.55,0,.35,1);}"
                 "@keyframes pen{0%{stroke-dashoffset:1600;fill-opacity:0}70%{stroke-dashoffset:0;fill-opacity:0}"
                 "100%{stroke-dashoffset:0;fill-opacity:1}}")
    gold_text_grad(d, "sigG", 720, 1140)
    d.t(sx, sy, 100, ("Suhail Chalil", "sig", "url(#sigG)"), anchor="end",
        cls="pen", extra=f'stroke="{GOLD_L}" stroke-width=".9" stroke-opacity=".9"')
    d.add(f'<line x1="830" y1="{sy + 44}" x2="{R}" y2="{sy + 44}" stroke="{GOLD}" stroke-opacity=".3"/>')
    d.t(R, sy + 74, 12, ("DESIGN · DEVELOPMENT · GROWTH", "mono", DIM), anchor="end", ls=2.6)

    # marquee
    my = 498
    d.add(f'<rect x="0" y="{my}" width="{W}" height="76" fill="{GOLD}" fill-opacity=".045"/>')
    d.add(f'<line x1="0" y1="{my}" x2="{W}" y2="{my}" stroke="{GOLD}" stroke-opacity=".25"/>')
    d.add(f'<line x1="0" y1="{my + 76}" x2="{W}" y2="{my + 76}" stroke="{GOLD}" stroke-opacity=".25"/>')
    words = ["Websites", "Mobile apps", "AI automation", "AI video", "Digital marketing", "Product design"]
    parts, x = [], 0.0
    for _ in range(2):
        for wd in words:
            role = "serif-i" if words.index(wd) % 2 else "serif"
            parts.append(d.text(x, my + 50, 34, (wd, role, IVORY if role == "serif" else GOLD_L)))
            x += tw(wd, role, 34) + 34
            parts.append(diamond(x, my + 39, 5, GOLD, .9))
            x += 34
    loop = x / 2
    d.css.append(f".mq{{animation:mq 36s linear infinite;}}@keyframes mq{{to{{transform:translateX(-{loop:.1f}px)}}}}")
    d.add(f'<g class="mq">{"".join(parts)}</g>')

    close_card(d)
    d.save("contact.svg")


def button(file: str, label: str, primary: bool) -> None:
    size = 15
    w = tw(label, "sans-b", size, .2) + 56
    h = 50
    d = Doc(round(w), h, label, label)
    if primary:
        d.defs.append(f'<linearGradient id="b" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{GOLD_L}"/>'
                      f'<stop offset="1" stop-color="{GOLD}"/></linearGradient>')
        d.add(f'<rect x=".5" y=".5" width="{w - 1:.1f}" height="{h - 1}" rx="{(h - 1) / 2}" fill="url(#b)"/>')
        fill = "#16130E"
    else:
        d.add(f'<rect x=".75" y=".75" width="{w - 1.5:.1f}" height="{h - 1.5}" rx="{(h - 1.5) / 2}" fill="#111110" '
              f'stroke="{GOLD}" stroke-opacity=".55" stroke-width="1.5"/>')
        fill = IVORY
    d.t(w / 2, h / 2 + 5.4, size, (label, "sans-b", fill), anchor="middle", ls=.2)
    d.save(file)


def main() -> None:
    ensure_fonts()
    ASSETS.mkdir(exist_ok=True)
    hero()
    about()
    invito()
    project("work-klack.svg", "N° 02", "E-COMMERCE CONCEPT", "https://suhailchalil.github.io/klack/",
            "KLACK", "storefront.",
            "An interactive mechanical keyboard storefront concept with layered motion, product storytelling and "
            "responsive design.",
            ["Layered, scroll-led motion", "Product storytelling", "Responsive on every screen"],
            "HTML · CSS · JavaScript", MEDIA / "klack.webp", "#7C4DFF", False)
    project("work-prime.svg", "N° 03", "CAMPAIGN HERO", "https://suhailchalil.github.io/prime-hydration/",
            "PRIME", "Hydration.",
            "A three-flavour campaign hero with swipe navigation and layered parallax, built in both vanilla "
            "JavaScript and Next.js.",
            ["Three flavours, swipe navigation", "Layered parallax", "Vanilla JS and Next.js builds"],
            "Next.js · React · JavaScript", MEDIA / "prime-hydration.webp", "#2F7BFF", True)
    project("work-rose-eternelle.svg", "N° 04", "SCROLL FILM · WEBGL", "https://suhailchalil.github.io/rose-eternelle/",
            "Rose", "Éternelle.",
            "A scroll-driven fragrance film that moves from video into a layered WebGL world and through a cloud "
            "transition.",
            ["Video into a layered WebGL world", "Scroll-driven art direction", "Cloud transition"],
            "Three.js · WebGL · JavaScript", MEDIA / "rose-eternelle.webp", "#E79AA7", False)
    approach()
    toolkit()
    contact()
    button("btn-case-study.svg", "Read the Invito Bello case study  ↗", True)
    button("btn-repositories.svg", "Browse all repositories  ↗", False)
    button("btn-live.svg", "Live demo  ↗", True)
    button("btn-source.svg", "Source code", False)


if __name__ == "__main__":
    main()
