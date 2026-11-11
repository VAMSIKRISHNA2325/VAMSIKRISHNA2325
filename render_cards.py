#!/usr/bin/env python3
"""Render a self-contained GitHub profile. STATIC=1 emits only the final frame."""

import argparse
import base64
import calendar
from collections import OrderedDict
from datetime import date, datetime, timedelta, timezone
from html import escape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
USERNAME = "VAMSIKRISHNA2325"
NAME = "Vamsikrishna"
NAME_LINES = ("Vamsi", "krishna.")
BIO = "Building useful tools, thoughtful interfaces, and applied ML."
GITHUB = f"https://github.com/{USERNAME}"
SOURCE = f"https://github.com/users/{USERNAME}/contributions"
DATA = ROOT / "data/contributions.json"
BG, ACCENT, INK = "#f3f3f1", "#2f55ff", "#111111"
MUTED, BORDER = "#6e6e73", "#dcdcd7"
LEVELS = ["#e2e2de", "#c8d3ff", "#94a8ff", "#6280ff", ACCENT]
TILE_COLORS = [ACCENT, "#ef3b2d", "#ffc81a"]
FONTS = [("Geist", "Geist.ttf", "100 900"),
         ("Serif", "InstrumentSerif-Regular.ttf", "400"),
         ("SerifItalic", "InstrumentSerif-Italic.ttf", "400"),
         ("Mono", "GeistMono.ttf", "100 900")]
# Set to None for a monogram. The supplied photo is rendered as ASCII.
PORTRAIT = ROOT / "assets/portrait.png"
# Normalized crop keeps the face and upper body legible at ASCII resolution.
PORTRAIT_CROP = (.39, .42, .69, .67)  # Set to None to use the whole image.
PROJECTS = [
    dict(slug="gesture_control", title="Gesture control", category="HUMAN-COMPUTER INTERACTION",
         description=["Control Windows with webcam hand gestures", "and offline voice commands."],
         tags=["Python", "MediaPipe", "OpenCV", "Vosk"],
         tile="Build", caption="Tools that respond to you.", mark="gesture"),
    dict(slug="f1-arch", title="F1 Arch", category="INTERACTIVE WEB",
         description=["A cinematic Formula 1 scroll experience", "exploring the car, cockpit, and livery."],
         tags=["TypeScript", "Next.js", "Framer Motion"],
         tile="Create", caption="Interfaces with a little motion.", mark="race"),
    dict(slug="PREDICTIVE-MODELING-OF-LASER-TREATED-METAL-SURFACES",
         title="Laser surface prediction", category="APPLIED MACHINE LEARNING",
         description=["Predict surface roughness and hardness", "through an interactive Streamlit interface."],
         tags=["Python", "scikit-learn", "Streamlit"],
         tile="Explore", caption="Patterns worth understanding.", mark="model"),
]


class CalendarParser(HTMLParser):
    """Join GitHub's date cells to their accessible, exact-count tooltips."""

    def __init__(self):
        super().__init__()
        self.cells, self.tips = {}, {}
        self.tip_id = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "data-date" in attrs and "data-level" in attrs:
            key = attrs["id"]
            if key in self.cells:
                raise ValueError("Duplicate contribution cell")
            self.cells[key] = (attrs["data-date"], int(attrs["data-level"]))
        if tag == "tool-tip" and attrs.get("for"):
            self.tip_id = attrs["for"]
            self.tips[self.tip_id] = ""

    def handle_data(self, data):
        if self.tip_id is not None:
            self.tips[self.tip_id] += data

    def handle_endtag(self, tag):
        if tag == "tool-tip":
            self.tip_id = None


def validate(snapshot):
    if snapshot.get("username") != USERNAME:
        raise ValueError("Contribution snapshot belongs to another user")
    end = date.fromisoformat(snapshot["asOf"])
    start = end - timedelta(days=364)
    days = snapshot["days"]
    expected = [(start + timedelta(days=i)).isoformat() for i in range(365)]
    if [d["date"] for d in days] != expected:
        raise ValueError("Expected 365 unique, consecutive, sorted dates ending on asOf")
    for d in days:
        if type(d["count"]) is not int or d["count"] < 0:
            raise ValueError("Invalid contribution count")
        if type(d["level"]) is not int or not 0 <= d["level"] <= 4:
            raise ValueError("Invalid contribution level")
        if (d["count"] == 0) != (d["level"] == 0):
            raise ValueError("Count and contribution level disagree")
    return snapshot


def parse_calendar(html, as_of):
    parser = CalendarParser()
    parser.feed(html)
    start = as_of - timedelta(days=364)
    days = []
    for key, (day, level) in parser.cells.items():
        if not start <= date.fromisoformat(day) <= as_of:
            continue
        tip = parser.tips.get(key, "").strip()
        match = re.match(r"^(No|[\d,]+) contributions? on\b", tip)
        if not match:
            raise ValueError(f"Missing or unrecognized contribution count for {day}")
        count = 0 if match[1] == "No" else int(match[1].replace(",", ""))
        days.append(dict(date=day, count=count, level=level))
    snapshot = dict(username=USERNAME, asOf=as_of.isoformat(), source=SOURCE,
                    days=sorted(days, key=lambda d: d["date"]))
    return validate(snapshot)


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as f:
        temporary = Path(f.name)
        f.write(content.encode("utf-8") if isinstance(content, str) else content)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def refresh():
    # Public calendar HTML has no stable API contract; fail closed if its markup changes.
    request = Request(SOURCE, headers={"User-Agent": "github-profile-cards",
                                      "Accept-Language": "en-US,en;q=0.9"})
    with urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8")
    snapshot = parse_calendar(html, datetime.now(timezone.utc).date())
    atomic_write(DATA, json.dumps(snapshot, indent=2) + "\n")
    print(f"Refreshed {len(snapshot['days'])} days through {snapshot['asOf']}")


def statistics(snapshot):
    validate(snapshot)
    days = snapshot["days"]
    by_date = {d["date"]: d["count"] for d in days}
    cursor = date.fromisoformat(snapshot["asOf"])
    if by_date[cursor.isoformat()] == 0:
        cursor -= timedelta(days=1)
    streak = 0
    while by_date.get(cursor.isoformat(), 0) > 0:
        streak += 1
        cursor -= timedelta(days=1)
    months = OrderedDict()
    for d in days:
        key = d["date"][:7]
        months[key] = months.get(key, 0) + d["count"]
    peak = max(days, key=lambda d: (d["count"], d["date"]))
    return dict(total=sum(by_date.values()), active=sum(n > 0 for n in by_date.values()),
                streak=streak, peak=peak if peak["count"] else None, months=months)


def text(x, y, value, size=20, fill=INK, cls="", extra=""):
    return (f'<text x="{x}" y="{y}" font-size="{size}" fill="{fill}" '
            f'class="{cls}" {extra}>{escape(str(value))}</text>')


def rule(y, x1=42, x2=958):
    return f'<path d="M{x1} {y}H{x2}" stroke="{BORDER}"/>'


def arrow(x, y, size=12, color=ACCENT):
    return (f'<path d="M{x} {y+size}l{size} -{size}m-{size} 0h{size}v{size}" '
            f'fill="none" stroke="{color}" stroke-width="1.5"/>')


def signal(x, y, delay, static):
    animation = "" if static else (
        f'<animate attributeName="opacity" values="0;0;1" '
        f'keyTimes="0;{delay/(delay+0.6):.5f};1" dur="{delay+0.6:.2f}s" '
        'begin="0s" repeatCount="1" fill="freeze"/>')
    return f'<circle class="signal" cx="{x}" cy="{y}" r="3.5" fill="{ACCENT}" opacity="1">{animation}</circle>'


def glyph(kind, x, y, scale=1):
    if kind == "gesture":
        shape = '<path d="M17 67V37a6 6 0 0 1 12 0v15-35a6 6 0 0 1 12 0v33-40a6 6 0 0 1 12 0v40-29a6 6 0 0 1 12 0v37l9-11a7 7 0 0 1 10 9L66 83H34L17 67Z"/>'
    elif kind == "race":
        shape = '<path d="M10 70h75M21 58l12-17h29l14 17H21Zm15-17 9-14h16l9 14M16 64h65"/><circle cx="31" cy="65" r="8"/><circle cx="68" cy="65" r="8"/>'
    else:
        shape = '<path d="M15 78V15m0 63h70M25 64l16-17 15 7 24-29"/><circle cx="25" cy="64" r="3"/><circle cx="41" cy="47" r="3"/><circle cx="56" cy="54" r="3"/><circle cx="80" cy="25" r="3"/>'
    return (f'<g transform="translate({x} {y}) scale({scale})" fill="none" '
            f'stroke="{ACCENT}" stroke-width="1.5" stroke-linecap="round" '
            f'stroke-linejoin="round">{shape}</g>')


def subset_fonts(body):
    from fontTools.ttLib import TTFont

    by_family = {}
    for node in ET.fromstring(f"<svg>{body}</svg>").iter("text"):
        classes = node.get("class", "").split()
        family = ("Mono" if "mono" in classes else "SerifItalic" if "italic" in classes
                  else "Serif" if "serif" in classes else "Geist")
        by_family[family] = by_family.get(family, "") + "".join(node.itertext())
    styles = []
    with tempfile.TemporaryDirectory() as tmp:
        chars = Path(tmp) / "glyphs.txt"
        for family, filename, weight in FONTS:
            visible = by_family.get(family, "")
            if not visible:
                continue
            chars.write_text("".join(sorted(set(visible))), encoding="utf-8")
            source = ROOT / "assets/fonts" / filename
            with TTFont(source) as font:
                missing = {ord(c) for c in visible if not c.isspace()} - font.getBestCmap().keys()
                if missing:
                    raise ValueError(f"{filename} lacks glyphs: {sorted(missing)}")
            target = Path(tmp) / f"{family}.woff"
            # This is pyftsubset's module entry point, independent of the shell's PATH.
            subprocess.run([sys.executable, "-m", "fontTools.subset", str(source),
                            f"--text-file={chars}", "--flavor=woff", f"--output-file={target}",
                            "--no-recalc-timestamp", "--canonical-order"], check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            data = base64.b64encode(target.read_bytes()).decode("ascii")
            styles.append(f"@font-face{{font-family:{family};src:url(data:font/woff;base64,{data}) "
                          f"format('woff');font-weight:{weight};font-style:normal;}}")
    return "\n".join(styles)


def svg(body, title, description, height, delay, static, width=1000, background=BG, motion="enter"):
    style = subset_fonts(body)
    style += "\ntext{font-family:Geist,sans-serif;font-weight:400}.mono{font-family:Mono,monospace}.serif{font-family:Serif,serif}.italic{font-family:SerifItalic,serif}.bold{font-weight:600}"
    if not static:
        style += f"""
        .enter{{animation:enter .8s ease-out {delay:.2f}s backwards}}
        .tile{{transform-origin:center;animation:swing 1.1s cubic-bezier(.2,.65,.25,1) {delay:.2f}s backwards}}
        .portrait-row{{animation:appear .3s ease-out var(--wait) backwards}}
        .bar{{transform-box:fill-box;transform-origin:center bottom;animation:grow .8s cubic-bezier(.2,.7,.2,1) backwards;animation-delay:var(--wait)}}
        .cell{{transform-box:fill-box;transform-origin:center;animation:pop .5s ease-out backwards;animation-delay:var(--wait)}}
        @keyframes enter{{from{{opacity:0;transform:translateY(10px)}}to{{opacity:1;transform:translateY(0)}}}}
        @keyframes grow{{from{{transform:scaleY(0)}}to{{transform:scaleY(1)}}}}
        @keyframes appear{{from{{opacity:0}}to{{opacity:1}}}}
        @keyframes pop{{0%{{opacity:0;transform:scale(.3)}}70%{{opacity:1;transform:scale(1.12)}}100%{{opacity:1;transform:scale(1)}}}}
        @keyframes swing{{0%{{opacity:0;transform:translateY(60px) scale(.75) rotate(-6deg)}}65%{{opacity:1;transform:translateY(-6px) scale(1.02) rotate(1deg)}}100%{{opacity:1;transform:none}}}}
        @media(prefers-reduced-motion:reduce){{
          *{{animation:none!important;transition:none!important}}
          .enter,.tile,.bar,.cell,.portrait-row{{opacity:1!important;transform:none!important}}
          .signal{{opacity:1!important}}
        }}
        """
    panel = (f'<rect x="{3 if width == 320 else 0}" y="0" width="{width-6 if width == 320 else width}" '
             f'height="{height}" rx="14" fill="{background}"/>')
    result = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
              f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">\n'
              f'<title id="title">{escape(title)}</title><desc id="desc">{escape(description)}</desc>\n'
              f'<defs><style>{style}</style></defs>\n'
              f'{panel if motion != "tile" else ""}\n'
              f'<g class="{motion}">{panel if motion == "tile" else ""}{body}</g>\n</svg>\n')
    check_svg(result, static)
    return result


def hero(static):
    body = text(48, 42, f"{USERNAME} / HELLO, WORLD", 12, MUTED, "mono")
    body += text(44, 166, NAME_LINES[0], 132, INK, "serif")
    body += text(44, 282, NAME_LINES[1], 132, ACCENT, "italic")
    body += text(49, 334, BIO, 18, "#3a3a3c")
    body += rule(371, 48, 952)
    body += signal(52, 404, .8, static)
    body += text(68, 409, "PYTHON  /  TYPESCRIPT  /  JAVA", 12, MUTED, "mono")
    body += text(950, 409, "ALWAYS BUILDING. ALWAYS LEARNING.", 10, MUTED, "mono", 'text-anchor="end"')
    if PORTRAIT:
        from PIL import Image, ImageOps

        with Image.open(PORTRAIT) as portrait:
            portrait = ImageOps.exif_transpose(portrait).convert("L")
            if PORTRAIT_CROP:
                box = tuple(round(v * (portrait.width if i % 2 == 0 else portrait.height))
                            for i, v in enumerate(PORTRAIT_CROP))
                portrait = portrait.crop(box)
            # Account for the physical aspect ratio of monospaced characters.
            portrait = ImageOps.fit(portrait, (276, 284)).resize((112, 90), Image.Resampling.LANCZOS)
            portrait = ImageOps.autocontrast(portrait, cutoff=1)
            ramp = " .,:;i1tfLCG08@"
            for row in range(portrait.height):
                line = "".join(ramp[(255-portrait.getpixel((col, row)))*(len(ramp)-1)//255]
                               for col in range(portrait.width))
                body += text(672, f"{61+row*3.15:.2f}", line, 4.1, INK, "mono portrait-row bold",
                             f'xml:space="preserve" style="--wait:{.15+row*.018:.3f}s"')
    else:
        body += text(820, 246, "vk", 150, INK, "italic", 'text-anchor="middle"')
    portrait_desc = "An ASCII portrait rendered from the supplied photograph." if PORTRAIT else "A personal monogram."
    return svg(body, f"{NAME} — {BIO}", "Python, TypeScript, and Java. " + portrait_desc, 440, .08, static)


def tile(project, index, static):
    ink = INK if index == 2 else "#ffffff"
    body = text(25, 34, f"0{index+1} / MY WORLD", 11, ink, "mono") + arrow(277, 23, color=ink)
    body += text(24, 115, project["tile"], 64, ink, "italic")
    body += text(26, 152, project["caption"], 13, ink)
    labels = ["GESTURE + VOICE", "WEB + MOTION", "DATA + PREDICTION"]
    body += text(26, 192, labels[index], 10, ink, "mono")
    return svg(body, project["tile"], project["caption"], 215, 3.1 + index*.25, static,
               320, TILE_COLORS[index], "tile")


def activity(snapshot, stats, static):
    body = text(42, 37, "SMALL STEPS, OVER TIME", 12, MUTED, "mono")
    body += text(42, 112, f"{stats['total']:,}", 76, INK, "serif")
    body += text(174, 105, "contributions", 20, "#3a3a3c")
    body += text(42, 327, f"{snapshot['days'][0]['date']}  —  {snapshot['asOf']} / UTC", 10, MUTED, "mono")
    months = list(stats["months"].items())
    maximum = max(1, max(n for _, n in months))
    ceiling = max(10, ((maximum + 49) // 50) * 50)
    left, base, plot_h, step = 66, 271, 126, 576 / len(months)
    for fraction in [0, .5, 1]:
        y = base - plot_h*fraction
        body += rule(y, left, 651)
        body += text(52, y+4, int(ceiling*fraction), 9, MUTED, "mono", 'text-anchor="end"')
    for i, (month, count) in enumerate(months):
        x = left + i*step + 9
        height = plot_h * count / ceiling
        if count:
            body += (f'<rect class="bar" style="--wait:{2.2+i*.045:.3f}s" x="{x:.2f}" '
                     f'y="{base-height:.2f}" width="{step-18:.2f}" height="{height:.2f}" '
                     f'rx="3" fill="{ACCENT if count == maximum else INK}"/>')
        else:
            body += f'<rect x="{x:.2f}" y="{base-2}" width="{step-18:.2f}" height="2" fill="{BORDER}"/>'
        if count:
            body += text(f"{x+(step-18)/2:.2f}", f"{base-height-8:.2f}", count, 9, MUTED, "mono", 'text-anchor="middle"')
        month_num = int(month[-2:])
        label = calendar.month_abbr[month_num]
        body += text(f"{x+(step-18)/2:.2f}", 293, label, 9, MUTED, "mono", 'text-anchor="middle"')
    body += f'<path d="M693 48V307" stroke="{BORDER}"/>'
    peak = stats["peak"]
    peak_day = date.fromisoformat(peak["date"]) if peak else None
    peak_label = f"{peak_day.day} {calendar.month_abbr[peak_day.month]}" if peak else "—"
    metrics = [(89, f"{stats['streak']} days", "CURRENT STREAK"),
               (180, str(stats["active"]), "ACTIVE DAYS"),
               (271, peak_label, f"BUSIEST DAY / {peak['count'] if peak else 0} CONTRIBUTIONS")]
    for y, value, label in metrics:
        body += text(734, y, value, 44, INK, "serif") + text(734, y+25, label, 10, MUTED, "mono")
    desc = (f"{stats['total']} contributions across {stats['active']} active days. Current streak: "
            f"{stats['streak']} days. Busiest day: {peak['date'] if peak else 'none'}, "
            f"{peak['count'] if peak else 0} contributions. Monthly totals: "
            + "; ".join(f"{m}: {n}" for m, n in months))
    return svg(body, "Monthly contributions and activity statistics", desc, 350, 2.0, static)


def repository(project, index, static):
    delay = 4.35 + index*.4
    body = text(42, 37, f"0{index+1} / SELECTED WORK", 11, MUTED, "mono")
    body += text(958, 37, project["category"], 10, ACCENT, "mono", 'text-anchor="end"')
    body += text(42, 92, project["title"], 47, INK, "serif")
    for line, value in enumerate(project["description"]):
        body += text(44, 129 + line*25, value, 18, "#3a3a3c")
    body += rule(175)
    body += text(44, 204, "  /  ".join(project["tags"]), 11, MUTED, "mono")
    body += glyph(project["mark"], 824, 58, .95) + arrow(943, 192)
    return svg(body, project["title"], " ".join(project["description"]) + " " + ", ".join(project["tags"]), 225, delay, static)


def graph(snapshot, stats, static):
    body = text(42, 32, "THE DAILY PRACTICE", 11, MUTED, "mono")
    body += text(42, 69, "The work, day by day.", 34, INK, "serif")
    body += signal(832, 28, .9, static) + text(847, 32, "LAST 365 DAYS", 11, MUTED, "mono")
    first = date.fromisoformat(snapshot["days"][0]["date"])
    sunday = first - timedelta(days=(first.weekday()+1) % 7)
    end = date.fromisoformat(snapshot["asOf"])
    columns = (end - sunday).days // 7 + 1
    pitch = min(17, 890 / columns)
    seen_months = set()
    for d in snapshot["days"]:
        day = date.fromisoformat(d["date"])
        col, row = divmod((day - sunday).days, 7)
        x, y = 69 + col*pitch, 108 + row*17
        month = day.strftime("%Y-%m")
        if month not in seen_months:
            seen_months.add(month)
            # A partial first month gets a label only if it leaves room for the next.
            if day == first and day.day > 14:
                pass
            else:
                body += text(f"{x:.2f}", 95, calendar.month_abbr[day.month], 10, MUTED, "mono")
        body += (f'<rect class="cell" style="--wait:{1+col*.018+row*.006:.3f}s" x="{x:.2f}" y="{y}" '
                 f'width="{pitch-4:.2f}" height="13" rx="2.5" fill="{LEVELS[d["level"]]}">'
                 f'<title>{d["date"]}: {d["count"]} contributions</title></rect>')
    for row, label in [(1, "M"), (3, "W"), (5, "F")]:
        body += text(43, 118+row*17, label, 10, MUTED, "mono")
    body += text(42, 254, f"{stats['active']} active days / {stats['total']} contributions", 11, MUTED, "mono")
    body += text(787, 254, "LESS", 9, MUTED, "mono")
    for i, color in enumerate(LEVELS):
        body += f'<rect x="{824+i*19}" y="243" width="13" height="13" rx="2.5" fill="{color}"/>'
    body += text(928, 254, "MORE", 9, MUTED, "mono")
    return svg(body, "Contribution graph", f"365 daily squares through {snapshot['asOf']}. "
               "Darker blue indicates more contributions. " +
               f"{stats['total']} contributions on {stats['active']} active days.", 280, .8, static)


def check_svg(source, static):
    tree = ET.fromstring(source)
    for node in tree.iter():
        tag = node.tag.rsplit("}", 1)[-1]
        if tag in {"script", "foreignObject"}:
            raise ValueError(f"Unsupported SVG element: {tag}")
        for name, value in node.attrib.items():
            if name.lower().startswith("on"):
                raise ValueError("SVG event handlers are not allowed")
            if name.endswith("href") and not value.startswith(("#", "data:")):
                raise ValueError("SVG assets must be embedded")
        if static and tag in {"animate", "animateTransform", "animateMotion", "set"}:
            raise ValueError("Static SVG contains animation")
    if "data:font/woff;base64," not in source:
        raise ValueError("Missing embedded fonts")
    if static and ("@keyframes" in source or "animation:" in source):
        raise ValueError("Static SVG contains CSS animation")


def render(static):
    snapshot = validate(json.loads(DATA.read_text(encoding="utf-8")))
    stats = statistics(snapshot)
    cards = {"hero.svg": hero(static)}
    for i, project in enumerate(PROJECTS):
        cards[f"tile-{i+1}.svg"] = tile(project, i, static)
    cards["activity.svg"] = activity(snapshot, stats, static)
    for i, project in enumerate(PROJECTS):
        cards[f"repo-{i+1}.svg"] = repository(project, i, static)
    cards["contributions.svg"] = graph(snapshot, stats, static)
    # Finish every render before replacing any outputs, so invalid input leaves old cards intact.
    for name, source in cards.items():
        atomic_write(ROOT / "cards" / name, source)
    graph_img = f'<a href="{GITHUB}?tab=overview"><img src="cards/contributions.svg" width="100%" alt="{stats["total"]} contributions on {stats["active"]} active days over the last 365 days." /></a>'
    activity_img = f'<img src="cards/activity.svg" width="100%" alt="{stats["total"]} contributions; {stats["active"]} active days; current streak {stats["streak"]} days. Monthly chart through {snapshot["asOf"]}." />'
    lines = [f'<a href="{GITHUB}"><img src="cards/hero.svg" width="100%" alt="{escape(NAME + ": " + BIO)}" /></a>',
             "", graph_img, "", activity_img, "", '<p align="center">']
    tiles = []
    for i, project in enumerate(PROJECTS):
        tiles.append(f'<a href="{GITHUB}/{project["slug"]}"><img src="cards/tile-{i+1}.svg" width="32.5%" alt="{project["tile"]}: {project["caption"]}" /></a>')
    # Inline whitespace can wrap the third image on narrow GitHub profile layouts.
    lines.append("".join(tiles))
    lines.extend(["</p>", ""])
    for i, project in enumerate(PROJECTS):
        alt = escape(project["title"] + ": " + " ".join(project["description"]))
        lines.extend([f'<a href="{GITHUB}/{project["slug"]}"><img src="cards/repo-{i+1}.svg" width="100%" alt="{alt}" /></a>', ""])
    readme = "\n".join(lines) + "\n"
    atomic_write(ROOT / "README.md", readme)
    preview = ('<!doctype html><html lang="en"><meta charset="utf-8">'
               '<meta name="viewport" content="width=device-width,initial-scale=1">'
               f'<title>{NAME} / Profile preview</title><style>'
               'body{margin:0;background:#ffffff;padding:40px 20px}main{max-width:1000px;margin:auto}'
               'img{height:auto;vertical-align:top}main>a,main>img{display:block;margin:0 0 14px}'
               'p{text-align:center;margin:0 0 14px}'
               '@media(max-width:600px){body{padding:16px 10px}}'
               '</style><main>' + readme + '</main></html>')
    atomic_write(ROOT / "preview.html", preview)
    print(f"Rendered {len(cards)} {'static' if static else 'animated'} cards; {stats['total']} real contributions. Open preview.html.")


def self_test():
    end = date(2024, 3, 1)
    days = [dict(date=(end-timedelta(days=364-i)).isoformat(), count=0, level=0) for i in range(365)]
    snap = dict(username=USERNAME, asOf=end.isoformat(), days=days)
    assert statistics(snap)["total"] == 0 and statistics(snap)["peak"] is None
    for i in [-3, -2]:
        days[i].update(count=5, level=4)
    s = statistics(snap)
    assert s["streak"] == 2 and s["active"] == 2 and s["peak"]["date"] == "2024-02-29"
    assert s["months"]["2024-02"] == 10 and sum(s["months"].values()) == s["total"]
    days[-1].update(count=1, level=1)
    assert statistics(snap)["streak"] == 3
    days[-2].update(count=0, level=0)
    assert statistics(snap)["streak"] == 1
    days[-1].update(count=0, level=0)
    assert statistics(snap)["streak"] == 0
    for bad in [dict(snap, days=days[:-1]), dict(snap, days=days+days[-1:]),
                dict(snap, username="someone-else"),
                dict(snap, days=[dict(d, count=-1) for d in days])]:
        try:
            validate(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid snapshot was accepted")
    html = "".join(f'<td id="d{i}" data-date="{d["date"]}" data-level="{d["level"]}"></td>'
                   f'<tool-tip for="d{i}">{d["count"] or "No"} contributions on a day.</tool-tip>'
                   for i, d in enumerate(days))
    assert parse_calendar(html, end)["days"] == days
    try:
        parse_calendar(html.replace('for="d1"', 'for="missing"'), end)
    except ValueError:
        pass
    else:
        raise AssertionError("Missing source count was accepted")
    print("Self-tests passed: streaks, leap day, zero activity, monthly sums, ties, invalid data, source parsing.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--refresh", action="store_true", help="Refresh public contribution JSON only")
    mode.add_argument("--self-test", action="store_true", help="Check parsing and contribution calculations")
    args = parser.parse_args()
    if args.refresh:
        refresh()
    elif args.self_test:
        self_test()
    else:
        render(os.environ.get("STATIC") == "1")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f"Profile generation failed: {error}", file=sys.stderr)
        sys.exit(1)
