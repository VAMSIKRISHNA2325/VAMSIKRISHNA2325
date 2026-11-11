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
    dict(slug="gesture_control", title="Gesture control",
         description=["Control Windows with webcam hand gestures", "and offline voice commands."],
         tags=["Python", "MediaPipe", "OpenCV", "Vosk"],
         tile="Build", caption="Tools that respond to you."),
    dict(slug="f1-arch", title="F1 Arch",
         description=["A cinematic Formula 1 scroll experience", "exploring the car, cockpit, and livery."],
         tags=["TypeScript", "Next.js", "Framer Motion"],
         tile="Create", caption="Interfaces with a little motion."),
    dict(slug="PREDICTIVE-MODELING-OF-LASER-TREATED-METAL-SURFACES",
         title="Laser surface prediction",
         description=["Predict surface roughness and hardness", "through an interactive Streamlit interface."],
         tags=["Python", "scikit-learn", "Streamlit"],
         tile="Explore", caption="Patterns worth understanding."),
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


def arrow(x, y, size=12, color=ACCENT, motion=""):
    return (f'<path class="{motion}" d="M{x} {y+size}l{size} -{size}m-{size} 0h{size}v{size}" '
            f'fill="none" stroke="{color}" stroke-width="1.5"/>')


def signal(x, y, delay, static):
    animation = "" if static else (
        f'<animate attributeName="opacity" values="0;0;1" '
        f'keyTimes="0;{delay/(delay+0.6):.5f};1" dur="{delay+0.6:.2f}s" '
        'begin="0s" repeatCount="1" fill="freeze"/>')
    return f'<circle class="signal" cx="{x}" cy="{y}" r="3.5" fill="{ACCENT}" opacity="1">{animation}</circle>'


def count_up(value, color, begin, static):
    final = text(24, 111, value, 56, color, "serif number-still")
    if static:
        return final
    finish = f'{begin + 1.1:.3f}s'
    frames = []
    for i in range(19):
        start = begin + i * 1.1 / 18
        stop = "" if i == 18 else (f'<set attributeName="opacity" to="0" '
                                       f'begin="{begin + (i+1)*1.1/18:.3f}s" fill="freeze"/>')
        number = round(value * (1 - (1-i/18)**3))
        frames.append(text(24, 111, number, 56, color, "serif",
                           'opacity="0"').replace('</text>',
                           f'<set attributeName="opacity" to="1" begin="{start:.3f}s" '
                           f'fill="freeze"/>{stop}</text>'))
    final = final.replace('class="serif number-still"',
                          f'class="serif number-still" style="--finish:{finish}"')
    return f'<g class="number-motion" style="--finish:{finish}">' + "".join(frames) + '</g>' + final


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
        .rise{{animation:enter .8s ease-out var(--wait) backwards}}
        .tile{{transform-origin:center;animation:swing 1.1s cubic-bezier(.2,.65,.25,1) {delay:.2f}s backwards}}
        .portrait-row{{animation:appear .3s ease-out var(--wait) backwards}}
        .bar{{transform-box:fill-box;transform-origin:center bottom;animation:grow .8s cubic-bezier(.2,.7,.2,1) backwards;animation-delay:var(--wait)}}
        .cell{{transform-box:fill-box;transform-origin:center;animation:pop .5s ease-out backwards;animation-delay:var(--wait)}}
        .signal{{animation:pulse 1.6s ease-in-out 1.6s infinite}}
        .nudge{{transform-box:fill-box;animation:nudge 1.8s ease-in-out 4.3s infinite}}
        .sheen{{animation:sheen 5s ease-in-out var(--wait) infinite}}
        .ring{{transform-box:fill-box;transform-origin:center;animation:ring 1s ease-out var(--wait) both}}
        .number-motion{{animation:hide-count .001s step-end var(--finish) forwards}}
        .number-still{{animation:show-count .001s step-end var(--finish) backwards}}
        @keyframes enter{{from{{opacity:0;transform:translateY(10px)}}to{{opacity:1;transform:translateY(0)}}}}
        @keyframes grow{{from{{transform:scaleY(0)}}to{{transform:scaleY(1)}}}}
        @keyframes appear{{from{{opacity:0}}to{{opacity:1}}}}
        @keyframes pop{{0%{{opacity:0;transform:scale(.3)}}70%{{opacity:1;transform:scale(1.12)}}100%{{opacity:1;transform:scale(1)}}}}
        @keyframes swing{{0%{{opacity:0;transform:translateY(60px) scale(.75) rotate(-6deg)}}65%{{opacity:1;transform:translateY(-6px) scale(1.02) rotate(1deg)}}100%{{opacity:1;transform:none}}}}
        @keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
        @keyframes nudge{{0%,100%{{transform:none}}50%{{transform:translate(3px,-2px)}}}}
        @keyframes sheen{{0%,12%{{transform:translateX(-80px)}}38%,100%{{transform:translateX(400px)}}}}
        @keyframes ring{{from{{opacity:.65;transform:scale(.2)}}to{{opacity:0;transform:scale(2.4)}}}}
        @keyframes hide-count{{to{{opacity:0}}}}
        @keyframes show-count{{from{{opacity:0}}to{{opacity:1}}}}
        @media(prefers-reduced-motion:reduce){{
          *{{animation:none!important;transition:none!important}}
          .enter,.rise,.tile,.bar,.cell,.portrait-row,.nudge{{opacity:1!important;transform:none!important}}
          .signal{{opacity:1!important}}
          .shine-overlay,.number-motion,.sheen,.ring{{display:none!important}}
          .number-still{{display:inline!important}}
        }}
        """
    panel = (f'<rect x="{3 if width == 320 else 0}" y="0" width="{width-6 if width == 320 else width}" '
             f'height="{height}" rx="14" fill="{background}"/>') if background else ""
    result = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
              f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">\n'
              f'<title id="title">{escape(title)}</title><desc id="desc">{escape(description)}</desc>\n'
              f'<defs><style>{style}</style></defs>\n'
              f'{panel if motion != "tile" else ""}\n'
              f'<g class="{motion}">{panel if motion == "tile" else ""}{body}</g>\n</svg>\n')
    check_svg(result, static)
    return result


def hero(static):
    body = text(48, 42, f"{USERNAME} / HELLO, WORLD", 12, MUTED, "mono rise", 'style="--wait:0s"')
    body += text(44, 166, NAME_LINES[0], 132, INK, "serif rise", 'style="--wait:.15s"')
    body += text(44, 282, NAME_LINES[1], 132, ACCENT, "italic rise", 'style="--wait:.30s"')
    if not static:
        body += (f'<defs><linearGradient id="name-shine" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="600" y2="0">'
                 f'<stop offset="0" stop-color="{ACCENT}"/><stop offset=".42" stop-color="{ACCENT}"/>'
                 f'<stop offset=".5" stop-color="#ffffff"/><stop offset=".58" stop-color="{ACCENT}"/>'
                 f'<stop offset="1" stop-color="{ACCENT}"/>'
                 '<animateTransform attributeName="gradientTransform" type="translate" '
                 'values="-600 0;600 0;600 0" keyTimes="0;.45;1" dur="7s" begin="1.6s" '
                 'repeatCount="indefinite"/></linearGradient></defs>')
        body += text(44, 282, NAME_LINES[1], 132, 'url(#name-shine)', "italic rise shine-overlay", 'style="--wait:.30s"')
    body += text(49, 334, BIO, 18, "#3a3a3c", "rise", 'style="--wait:.55s"')
    body += rule(371, 48, 952)
    body += '<g class="rise" style="--wait:.8s">' + signal(52, 404, .8, static)
    body += text(68, 409, "PYTHON  /  TYPESCRIPT  /  JAVA", 12, MUTED, "mono")
    body += text(950, 409, "ALWAYS BUILDING. ALWAYS LEARNING.", 10, MUTED, "mono", 'text-anchor="end"') + '</g>'
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
                             f'xml:space="preserve" style="--wait:{.25+row*.018:.3f}s"')
    else:
        body += text(820, 246, "vk", 150, INK, "italic", 'text-anchor="middle"')
    portrait_desc = "An ASCII portrait rendered from the supplied photograph." if PORTRAIT else "A personal monogram."
    return svg(body, f"{NAME} — {BIO}", "Python, TypeScript, and Java. " + portrait_desc, 440, .08, static, motion="plain")


def tile(project, index, stats, static):
    ink = INK if index == 2 else "#ffffff"
    delay = 3.1 + index*.25
    value, unit = [(len(PROJECTS), "projects"), (stats["active"], "active days"),
                   (stats["total"], "contributions")][index]
    body = text(25, 34, f"0{index+1} / {project['tile'].upper()}", 11, ink, "mono")
    body += arrow(277, 23, color=ink, motion="nudge")
    if not static:
        body += ('<defs><clipPath id="tile-clip"><rect x="3" y="0" width="314" height="215" rx="14"/></clipPath>'
                 '<linearGradient id="tile-shine"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
                 '<stop offset=".5" stop-color="#fff" stop-opacity=".35"/>'
                 '<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>')
        body += (f'<g clip-path="url(#tile-clip)"><circle class="ring" style="--wait:{delay+.5:.2f}s" '
                 f'cx="275" cy="174" r="38" fill="none" stroke="{ink}" stroke-opacity=".5" stroke-width="2"/>'
                 f'<rect class="sheen" style="--wait:{delay+1.4:.2f}s" x="-80" y="-10" width="80" '
                 'height="235" fill="url(#tile-shine)"/></g>')
    body += count_up(value, ink, delay+.45, static)
    body += text(24, 141, unit, 28, ink, "italic")
    body += text(26, 171, project["caption"], 13, ink)
    labels = ["GESTURE + VOICE", "WEB + MOTION", "DATA + PREDICTION"]
    body += text(26, 197, labels[index], 10, ink, "mono")
    return svg(body, project["tile"], f"{value} {unit}. {project['caption']}", 215, delay, static,
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
    metrics = [(89, f"{stats['streak']} {'day' if stats['streak'] == 1 else 'days'}", "CURRENT STREAK"),
               (180, str(stats["active"]), "ACTIVE DAYS"),
               (271, peak_label, f"BUSIEST DAY / {peak['count'] if peak else 0} CONTRIBUTIONS")]
    for y, value, label in metrics:
        body += text(734, y, value, 44, INK, "serif") + text(734, y+25, label, 10, MUTED, "mono")
    desc = (f"{stats['total']} contributions across {stats['active']} active days. Current streak: "
            f"{stats['streak']} {'day' if stats['streak'] == 1 else 'days'}. Busiest day: {peak['date'] if peak else 'none'}, "
            f"{peak['count'] if peak else 0} contributions. Monthly totals: "
            + "; ".join(f"{m}: {n}" for m, n in months))
    return svg(body, "Monthly contributions and activity statistics", desc, 350, 2.0, static)


def repository(project, index, static):
    delay = 4.65 + index*.12
    names = ["Gesture control", "F1 Arch", "Laser surface ML"]
    blurbs = [("Hands-free Windows control", "by gesture and voice."),
              ("A cinematic Formula 1", "scroll experience."),
              ("Predict roughness and", "hardness after laser treatment.")]
    languages = ["Python", "TypeScript", "Python"]
    body = f'<rect x="24" y="26" width="8" height="8" rx="2" fill="{TILE_COLORS[index]}"/>'
    body += text(24, 73, names[index], 32, INK, "serif")
    for line, value in enumerate(blurbs[index]):
        body += text(24, 108 + line*20, value, 14, "#3a3a3c")
    body += rule(148, 24, 296)
    body += text(24, 174, languages[index], 11, MUTED, "mono") + arrow(278, 159)
    return svg(body, project["title"], " ".join(project["description"]) + " " + ", ".join(project["tags"]), 190, delay, static, 320)


def section_title(dark, static):
    ink = "#e6edf3" if dark else INK
    body = text(18, 54, "What I'm", 52, ink, "serif")
    body += text(222, 54, "building", 52, ACCENT, "italic")
    return svg(body, "What I'm building", "Selected projects", 76, 4.4, static, background=None)


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
        cards[f"tile-{i+1}.svg"] = tile(project, i, stats, static)
    cards["activity.svg"] = activity(snapshot, stats, static)
    cards["title-building-light.svg"] = section_title(False, static)
    cards["title-building-dark.svg"] = section_title(True, static)
    for i, project in enumerate(PROJECTS):
        cards[f"repo-{i+1}.svg"] = repository(project, i, static)
    cards["contributions.svg"] = graph(snapshot, stats, static)
    # Finish every render before replacing any outputs, so invalid input leaves old cards intact.
    for name, source in cards.items():
        atomic_write(ROOT / "cards" / name, source)
    graph_img = f'<a href="{GITHUB}?tab=overview"><img src="cards/contributions.svg" width="100%" alt="{stats["total"]} contributions on {stats["active"]} active days over the last 365 days." /></a>'
    activity_img = f'<img src="cards/activity.svg" width="100%" alt="{stats["total"]} contributions; {stats["active"]} active days; current streak {stats["streak"]} {"day" if stats["streak"] == 1 else "days"}. Monthly chart through {snapshot["asOf"]}." />'
    lines = [f'<a href="{GITHUB}"><img src="cards/hero.svg" width="100%" alt="{escape(NAME + ": " + BIO)}" /></a>',
             "", graph_img, "", activity_img, "", '<p align="center">']
    tiles = []
    values = [len(PROJECTS), stats["active"], stats["total"]]
    units = ["featured projects", "active days", "contributions"]
    for i, project in enumerate(PROJECTS):
        tiles.append(f'<a href="{GITHUB}/{project["slug"]}"><img src="cards/tile-{i+1}.svg" width="32.5%" alt="{project["tile"]}: {values[i]} {units[i]}. Opens {project["title"]}." /></a>')
    # Inline whitespace can wrap the third image on narrow GitHub profile layouts.
    lines.append("".join(tiles))
    lines.extend(["</p>", "", '<picture><source media="(prefers-color-scheme: dark)" srcset="cards/title-building-dark.svg" /><img src="cards/title-building-light.svg" width="100%" alt="What I\'m building" /></picture>', "", '<p align="center">'])
    repos = []
    for i, project in enumerate(PROJECTS):
        alt = escape(project["title"] + ": " + " ".join(project["description"]))
        repos.append(f'<a href="{GITHUB}/{project["slug"]}"><img src="cards/repo-{i+1}.svg" width="32.5%" alt="{alt}" /></a>')
    lines.extend(["".join(repos), "</p>"])
    readme = "\n".join(lines) + "\n"
    atomic_write(ROOT / "README.md", readme)
    preview = ('<!doctype html><html lang="en"><meta charset="utf-8">'
               '<meta name="viewport" content="width=device-width,initial-scale=1">'
               f'<title>{NAME} / Profile preview</title><style>'
               'body{margin:0;background:#ffffff;padding:40px 20px}main{max-width:1000px;margin:auto}'
               'img{height:auto;vertical-align:top}main>a,main>img,main>picture{display:block;margin:0 0 14px}'
               'p{text-align:center;margin:0 0 14px}'
               '@media(max-width:600px){body{padding:16px 10px}}'
               '@media(prefers-color-scheme:dark){body{background:#0d1117}}'
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
    animated = count_up(32, INK, 3.5, False)
    assert animated.count('<set ') == 37 and 'number-motion' in animated and '>32</text>' in animated
    assert '<set ' not in count_up(32, INK, 3.5, True)
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
