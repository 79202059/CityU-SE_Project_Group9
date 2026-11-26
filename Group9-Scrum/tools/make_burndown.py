#!/usr/bin/env python3
"""Regenerate burndown / velocity charts from CSV data (stdlib only).

Usage:
    python tools/make_burndown.py

Inputs
    data/burndown-sprint-1.csv
    data/burndown-sprint-2.csv
    data/burndown-sprint-3.csv
    data/burndown-project.csv
    data/velocity.csv

Outputs
    charts/burndown-sprint-1.svg ... charts/velocity.svg
    burndown.html   (self-contained dashboard: inline SVG + data tables)

CSV columns
    sprint/1/2/3 : day,date,remaining_sp,forecast,today,note
    project      : week,date,remaining_sp,forecast,today,note
    velocity     : sprint,label,committed,completed,status
"""

from __future__ import annotations

import csv
import html
import math
import os
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CHARTS = os.path.join(ROOT, "charts")

W, H = 920, 470
ML, MR, MT, MB = 74, 44, 88, 84
PW, PH = W - ML - MR, H - MT - MB

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

BLUE = "#2563eb"
SLATE = "#475569"
MUTED = "#94a3b8"
GRID = "#e8ebf0"
AMBER = "#d97706"
INK = "#0f172a"


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def short_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{MONTHS[d.month - 1]} {d.day}"


def read_rows(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for pos, row in enumerate(rows):
        key = row.get("day", row.get("week"))
        out.append({
            "idx": int(key if key is not None else pos),
            "date": row["date"],
            "remaining": float(row["remaining_sp"]),
            "forecast": row.get("forecast", "0").strip() == "1",
            "today": row.get("today", "0").strip() == "1",
            "note": (row.get("note") or "").strip(),
        })
    return out


def text(x, y, s, size=11, fill=SLATE, anchor="start", weight="400") -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" '
            f'text-anchor="{anchor}" font-weight="{weight}">{esc(s)}</text>')


def path_of(points) -> str:
    return "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in points)


def nice_step(top: float) -> int:
    if top <= 10:
        return 2
    if top <= 40:
        return 5
    return 10


def x_stride(n: int) -> int:
    if n <= 12:
        return 1
    return 4


def build_burndown(rows, title, subtitle, source, outfile, extra_note="") -> str:
    n = max(r["idx"] for r in rows)
    start = rows[0]["remaining"]
    step = nice_step(start)
    ymax = int(math.ceil(start / step) * step)
    if ymax == 0:
        ymax = step

    def X(i: float) -> float:
        return ML + PW * (i / n) if n else ML

    def Y(v: float) -> float:
        return MT + PH * (1 - v / ymax)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="100%" role="img" aria-label="{esc(title)}">',
        f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
        f'<style>text{{font-family:"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}}</style>',
        text(ML, 34, title, 19, INK, weight="600"),
        text(ML, 56, subtitle, 12.5, "#64748b"),
    ]

    # legend (top right); forecast entry only when this chart has one
    has_forecast = any(r["forecast"] for r in rows)
    legend = [("actual", False, BLUE), ("ideal", True, "#a8b3c1")]
    if has_forecast:
        legend.insert(1, ("forecast", True, BLUE))
    lx, ly = W - MR - 82 * len(legend), 34
    for label, dashed, colour in legend:
        parts.append(f'<line x1="{lx:.0f}" y1="{ly - 4}" x2="{lx + 22:.0f}" y2="{ly - 4}" '
                     f'stroke="{colour}" stroke-width="2.4"'
                     + (f' stroke-dasharray="5 4"' if dashed else "") + "/>")
        parts.append(text(lx + 27, ly, label, 11, "#64748b"))
        lx += 82

    # y grid + labels
    for v in range(0, ymax + 1, step):
        y = Y(v)
        parts.append(f'<line x1="{ML}" y1="{y:.1f}" x2="{ML + PW}" y2="{y:.1f}" '
                     f'stroke="{GRID}" stroke-width="1"/>')
        parts.append(text(ML - 12, y + 4, f"{v}", 11, MUTED, anchor="end"))
    parts.append(text(18, MT + PH / 2, "Story points remaining", 11, "#64748b",
                      anchor="middle")
                 .replace('<text ', f'<text transform="rotate(-90 18 {MT + PH / 2:.0f})" '))

    # x labels
    stride = x_stride(n)
    label_idx = set(range(0, n + 1, stride)) | {n}
    for i in sorted(label_idx):
        row = next((r for r in rows if r["idx"] == i), None)
        if row is None:
            continue
        parts.append(text(X(i), MT + PH + 22, short_date(row["date"]), 10.5, MUTED,
                          anchor="middle"))
    parts.append(text(ML + PW / 2, H - 46, "Sprint duration" if n <= 20 else "Project weeks",
                      11, "#64748b", anchor="middle"))

    # ideal
    parts.append(f'<line x1="{X(0):.1f}" y1="{Y(start):.1f}" x2="{X(n):.1f}" y2="{Y(0):.1f}" '
                 f'stroke="#a8b3c1" stroke-width="2" stroke-dasharray="6 5"/>')

    actual = [r for r in rows if not r["forecast"]]
    forecast = [r for r in rows if r["forecast"]]

    # area under actual
    if len(actual) >= 2:
        pts = [(X(r["idx"]), Y(r["remaining"])) for r in actual]
        area = path_of(pts) + f" L {pts[-1][0]:.1f} {Y(0):.1f} L {pts[0][0]:.1f} {Y(0):.1f} Z"
        parts.append(f'<path d="{area}" fill="{BLUE}" opacity="0.06"/>')

    if len(actual) >= 2:
        parts.append(f'<path d="{path_of([(X(r["idx"]), Y(r["remaining"])) for r in actual])}" '
                     f'fill="none" stroke="{BLUE}" stroke-width="2.8" '
                     f'stroke-linejoin="round" stroke-linecap="round"/>')
    if forecast:
        chain = [actual[-1]] + forecast if actual else forecast
        parts.append(f'<path d="{path_of([(X(r["idx"]), Y(r["remaining"])) for r in chain])}" '
                     f'fill="none" stroke="{BLUE}" stroke-width="2.4" opacity="0.55" '
                     f'stroke-dasharray="6 5" stroke-linejoin="round"/>')

    # dots
    for r in rows:
        fill = "#ffffff" if r["forecast"] else BLUE
        parts.append(
            f'<circle cx="{X(r["idx"]):.1f}" cy="{Y(r["remaining"]):.1f}" r="3.5" '
            f'fill="{fill}" stroke="{BLUE}" stroke-width="1.6"'
            + (' opacity="0.6"' if r["forecast"] else "") + ">"
            f"<title>{esc(short_date(r['date']))}: {r['remaining']:.0f} SP — {esc(r['note'])}</title>"
            "</circle>")

    # today marker
    today = next((r for r in rows if r["today"]), None)
    if today:
        xt = X(today["idx"])
        parts.append(f'<line x1="{xt:.1f}" y1="{MT}" x2="{xt:.1f}" y2="{MT + PH}" '
                     f'stroke="{AMBER}" stroke-width="1.3" stroke-dasharray="3 4"/>')
        parts.append(text(xt + 5, MT + 12, "today", 10.5, "#b45309", weight="600"))

    last = actual[-1] if actual else rows[0]
    annotate_idx = last["idx"] if last["remaining"] > 0 else None

    # value labels on drops
    prev = None
    for r in rows:
        if (prev is not None and r["remaining"] < prev - 0.5
                and r["idx"] != annotate_idx):
            parts.append(text(X(r["idx"]), Y(r["remaining"]) - 10, f'{r["remaining"]:.0f}',
                              10.5, INK, anchor="middle", weight="600"))
        prev = r["remaining"]

    if last["remaining"] > 0:
        x_last = X(last["idx"])
        anchor = "end" if x_last > W - MR - 70 else "middle"
        parts.append(text(x_last, Y(last["remaining"]) - 14,
                          f'{last["remaining"]:.0f} SP left', 11, "#b45309",
                          anchor=anchor, weight="600"))

    if extra_note:
        parts.append(text(ML + PW, MT + PH - 12, extra_note, 11, "#64748b", anchor="end"))

    foot = f"Source: {source}"
    if has_forecast:
        foot += "  ·  dashed segment = forecast"
    foot += "  ·  generated 2026-11-26"
    parts.append(text(ML, H - 18, foot, 10.5, MUTED))
    parts.append("</svg>")

    svg = "\n".join(parts)
    os.makedirs(CHARTS, exist_ok=True)
    with open(os.path.join(CHARTS, outfile), "w", encoding="utf-8") as fh:
        fh.write(svg)
    return svg


def build_velocity(path: str) -> str:
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))

    w, h = 920, 360
    ml, mr, mt, mb = 74, 44, 84, 96
    pw, ph = w - ml - mr, h - mt - mb
    top = max(int(r["committed"]) for r in rows)
    step = 5
    ymax = int(math.ceil(top / step) * step) + step

    def Y(v: float) -> float:
        return mt + ph * (1 - v / ymax)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" '
        f'role="img" aria-label="Velocity by sprint">',
        f'<rect width="{w}" height="{h}" fill="#ffffff"/>',
        '<defs><pattern id="hatch" width="6" height="6" patternTransform="rotate(45)" '
        'patternUnits="userSpaceOnUse"><line x1="0" y1="0" x2="0" y2="6" '
        'stroke="#2563eb" stroke-width="2" opacity="0.35"/></pattern></defs>',
        f'<style>text{{font-family:"Segoe UI",Roboto,Helvetica,Arial,sans-serif;}}</style>',
        text(ml, 34, "Velocity — committed vs completed story points", 19, INK, weight="600"),
        text(ml, 56, "Bar height = story points. Sprint 3 completed value is a forecast "
                     "(22 of 30 SP delivered by Week 12).", 12, "#64748b"),
    ]

    for v in range(0, ymax + 1, step):
        y = Y(v)
        parts.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{ml + pw}" y2="{y:.1f}" '
                     f'stroke="{GRID}" stroke-width="1"/>')
        parts.append(text(ml - 12, y + 4, f"{v}", 11, MUTED, anchor="end"))

    group = pw / len(rows)
    bar_w = min(52, group * 0.28)
    for pos, r in enumerate(rows):
        committed, completed = int(r["committed"]), int(r["completed"])
        cx = ml + group * (pos + 0.5)
        x1, x2 = cx - bar_w - 6, cx + 6

        parts.append(f'<rect x="{x1:.1f}" y="{Y(committed):.1f}" width="{bar_w:.1f}" '
                     f'height="{Y(0) - Y(committed):.1f}" rx="4" fill="#cbd5e1"/>')
        parts.append(text(x1 + bar_w / 2, Y(committed) - 8, f"{committed}", 11.5, SLATE,
                          anchor="middle", weight="600"))

        parts.append(f'<rect x="{x2:.1f}" y="{Y(completed):.1f}" width="{bar_w:.1f}" '
                     f'height="{Y(0) - Y(completed):.1f}" rx="4" fill="{BLUE}"/>')
        if completed < committed:
            parts.append(f'<rect x="{x2:.1f}" y="{Y(committed):.1f}" width="{bar_w:.1f}" '
                         f'height="{Y(completed) - Y(committed):.1f}" rx="4" fill="url(#hatch)"/>')
        parts.append(text(x2 + bar_w / 2, Y(completed) - 8,
                          f"{completed}" + ("*" if completed < committed else ""),
                          11.5, BLUE, anchor="middle", weight="600"))

        label = r["label"]
        name, _, span = label.partition(" (")
        parts.append(text(cx, mt + ph + 26, name, 12, INK, anchor="middle", weight="600"))
        parts.append(text(cx, mt + ph + 44, "(" + span if span else "", 10.5, MUTED,
                          anchor="middle"))

    parts.append(text(ml + pw / 2, h - 30, "Sprint", 11, "#64748b", anchor="middle"))
    parts.append(text(18, mt + ph / 2, "Story points", 11, "#64748b", anchor="middle")
                 .replace('<text ', f'<text transform="rotate(-90 18 {mt + ph / 2:.0f})" '))
    parts.append(text(ml, h - 10, "grey = committed · blue = completed · hatched = forecast "
                                   "remainder · * = forecast", 10.5, MUTED))
    parts.append("</svg>")

    svg = "\n".join(parts)
    os.makedirs(CHARTS, exist_ok=True)
    with open(os.path.join(CHARTS, "velocity.svg"), "w", encoding="utf-8") as fh:
        fh.write(svg)
    return svg


def data_table(rows, first_col: str) -> str:
    out = [
        "<table>",
        f"<thead><tr><th>{esc(first_col)}</th><th>Date</th>"
        "<th class='num'>Remaining SP</th><th>Event</th></tr></thead><tbody>",
    ]
    for r in rows:
        cls = " ".join(c for c, on in (("forecast", r["forecast"]), ("today", r["today"])) if on)
        out.append(
            f"<tr class='{cls}'><td>{r['idx']}</td><td>{esc(r['date'])}</td>"
            f"<td class='num'>{r['remaining']:.0f}</td><td>{esc(r['note'])}</td></tr>"
        )
    out.append("</tbody></table>")
    return "\n".join(out)


CSS = """
:root{--ink:#0f172a;--slate:#475569;--muted:#94a3b8;--line:#e2e8f0;--bg:#f6f8fb;
--card:#fff;--blue:#2563eb;--amber:#d97706}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font-family:"Segoe UI",Roboto,Helvetica,Arial,"PingFang SC","Microsoft YaHei",sans-serif;
line-height:1.55}
.wrap{max-width:1120px;margin:0 auto;padding:40px 28px 72px}
.eyebrow{letter-spacing:.14em;text-transform:uppercase;font-size:11.5px;color:var(--blue);
font-weight:700}
h1{font-size:32px;line-height:1.2;margin:10px 0 8px}
h2{font-size:20px;margin:0 0 4px}
h3{font-size:15px;margin:26px 0 8px}
p{margin:8px 0;color:var(--slate)}
.lede{font-size:15px;max-width:820px}
.badges{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 4px}
.badge{background:#e8f0fe;color:#1d4ed8;border-radius:999px;padding:4px 12px;
font-size:12px;font-weight:600}
.badge.warn{background:#fef3c7;color:#92400e}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;
margin:26px 0 8px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px}
.kpi .v{font-size:26px;font-weight:700;letter-spacing:-.02em}
.kpi .v.sm{font-size:18px;letter-spacing:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.kpi .l{font-size:11.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;
margin-top:2px}
.kpi .s{font-size:12px;color:var(--slate);margin-top:6px}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:22px 24px;
margin:20px 0;box-shadow:0 1px 2px rgba(15,23,42,.04)}
.meta{font-size:12.5px;color:var(--muted);margin-bottom:10px}
svg{display:block}
table{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:14px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid #eef2f7;vertical-align:top}
th{font-size:11px;text-transform:uppercase;letter-spacing:.07em;color:var(--muted);
font-weight:600}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tbody tr:nth-child(even){background:#fbfcfe}
tr.forecast td{color:#94a3b8;font-style:italic}
tr.today td{background:#fffbeb}
.grid2{display:grid;grid-template-columns:1fr;gap:20px}
.note{background:#fffbeb;border:1px solid #fde68a;border-radius:12px;padding:14px 18px;
font-size:13px;color:#78350f}
.note b{color:#92400e}
footer{margin-top:36px;font-size:12px;color:var(--muted);border-top:1px solid var(--line);
padding-top:16px}
@media print{body{background:#fff}.card{box-shadow:none;break-inside:avoid}
.wrap{max-width:none;padding:0}}
@media (min-width:980px){.grid2{grid-template-columns:1fr 1fr}}
"""


def main() -> None:
    sprint_specs = [
        ("burndown-sprint-1.csv", "Sprint 1 — Baseline & core model",
         "Sep 14 – Oct 9, 2026 · Weeks 2–5 · 21 SP committed · 21 SP delivered", 1),
        ("burndown-sprint-2.csv", "Sprint 2 — Matching & calibration",
         "Oct 12 – Nov 6, 2026 · Weeks 6–9 · 21 SP committed · 21 SP delivered", 2),
        ("burndown-sprint-3.csv", "Sprint 3 — Integration & evaluation",
         "Nov 9 – Dec 4, 2026 · Weeks 10–13 · 30 SP committed · 22 SP delivered by Week 12, "
         "8 SP forecast", 3),
    ]

    generated = {}
    cards = []
    for filename, title, subtitle, num in sprint_specs:
        rows = read_rows(os.path.join(DATA, filename))
        svg = build_burndown(rows, title, subtitle, f"data/{filename}",
                             f"burndown-sprint-{num}.svg")
        generated[f"sprint{num}"] = svg
        cards.append(
            f'<section class="card">{svg}'
            f'<p class="meta" style="margin:18px 0 0">Daily trace — '
            f'<code>data/{filename}</code></p>'
            f'{data_table(rows, "Working day")}</section>'
        )

    proj_rows = read_rows(os.path.join(DATA, "burndown-project.csv"))
    proj_svg = build_burndown(proj_rows, "Project burndown — all three sprints",
                              "Sep 14 – Dec 4, 2026 · 72 SP total scope · 64 SP accepted by "
                              "Nov 26 · 8 SP forecast for Week 13",
                              "data/burndown-project.csv", "burndown-project.svg")
    vel_svg = build_velocity(os.path.join(DATA, "velocity.csv"))

    with open(os.path.join(DATA, "velocity.csv"), newline="", encoding="utf-8") as fh:
        vel_rows = list(csv.DictReader(fh))
    vel_table = ["<table><thead><tr><th>Sprint</th><th class='num'>Committed</th>"
                 "<th class='num'>Completed</th><th>Status</th></tr></thead><tbody>"]
    for r in vel_rows:
        vel_table.append(
            f"<tr><td>{esc(r['label'])}</td><td class='num'>{r['committed']}</td>"
            f"<td class='num'>{r['completed']}</td><td>{esc(r['status'])}</td></tr>")
    vel_table.append("</tbody></table>")
    vel_table = "\n".join(vel_table)

    total_scope = int(proj_rows[0]["remaining"])
    delivered = sum(int(r["completed"]) for r in vel_rows)

    body = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>PyExamine-Delta — Burndown Dashboard</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<div class="eyebrow">CS5351 Software Engineering · Group 9 · Scrum evidence</div>
<h1>PyExamine-Delta — sprint burndown dashboard</h1>
<p class="lede">Change-aware code smell detection for Python pull requests. Story-point scope,
ideal vs actual burndown, and velocity for three sprints (Weeks 2–13). Everything on this page
is generated from the CSV files in <code>data/</code> by <code>tools/make_burndown.py</code>.</p>
<div class="badges">
<span class="badge">Snapshot: 2026-11-26 (Week 12)</span>
<span class="badge warn">Sprint 3 days 14–20 are forecast</span>
</div>

<div class="kpis">
<div class="kpi"><div class="l">Total scope</div><div class="v">{total_scope} SP</div>
<div class="s">19 user stories · 5 epics</div></div>
<div class="kpi"><div class="l">Accepted</div><div class="v">{delivered} SP</div>
<div class="s">{delivered / total_scope:.0%} of committed scope</div></div>
<div class="kpi"><div class="l">Velocity</div><div class="v sm">21&nbsp;/&nbsp;21&nbsp;/&nbsp;30</div>
<div class="s">SP per sprint (S3 in progress)</div></div>
<div class="kpi"><div class="l">Automated tests</div><div class="v">431</div>
<div class="s">216 upstream + 215 new</div></div>
<div class="kpi"><div class="l">Stable rule ids</div><div class="v">47</div>
<div class="s">pyex-&lt;category&gt;-&lt;slug&gt;</div></div>
<div class="kpi"><div class="l">New tool code</div><div class="v">~3.6k</div>
<div class="s">12 delta modules, Python 3.10+</div></div>
</div>

{''.join(cards)}

<section class="card">
<div class="meta">Weekly checkpoints across the 12-week project; the last segment is the
Week 13 forecast.</div>
{proj_svg}
{data_table(proj_rows, "Week")}
</section>

<section class="card">
<div class="meta">Committed vs completed story points. Sprint 3 shows the 22 SP already
accepted plus the 8 SP evaluation story still in progress.</div>
{vel_svg}
{vel_table}
</section>

<section class="card">
<h2>How to keep this page current</h2>
<p>1. After the weekly standing meeting, append or edit the matching row in
<code>data/burndown-sprint-N.csv</code> (remaining story points and a one-line event).</p>
<p>2. Flip <code>forecast</code> from <code>1</code> to <code>0</code> when a day becomes
history, and move the <code>today</code> flag to the current working day.</p>
<p>3. Regenerate everything:</p>
<p><code>python tools/make_burndown.py</code> — rewrites <code>charts/*.svg</code> and this
file.</p>
<div class="note"><b>Data provenance.</b> Scope, sprint boundaries and story points are the
team's planning records. Test counts, rule ids, module inventory and the ADR-008 date were
taken from the repository on 2026-11-25. Meeting-by-meeting values must be reconciled with the
Scrum Master's notes before submission; nothing here is measured telemetry.</div>
</section>

<footer>Group 9 · CS5351 Software Engineering · CityU (Dongguan) · generated by
tools/make_burndown.py</footer>
</div>
</body>
</html>
"""

    with open(os.path.join(ROOT, "burndown.html"), "w", encoding="utf-8") as fh:
        fh.write(body)

    print("Wrote charts:", ", ".join(sorted(os.listdir(CHARTS))))
    print("Wrote burndown.html")


if __name__ == "__main__":
    main()