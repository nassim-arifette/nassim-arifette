"""Generate the profile SVG cards (stats, languages, contribution graph) from the GitHub API.

Runs in the daily workflow with GITHUB_TOKEN. Usage: python scripts/cards.py <login> <out_dir>
"""
import datetime as dt
import json
import os
import sys
import urllib.request
from html import escape

LOGIN, OUT = sys.argv[1], sys.argv[2]
TOKEN = os.environ["GITHUB_TOKEN"]

BG, BORDER, TEXT, MUTED, ACCENT = "#0d1117", "#30363d", "#c9d1d9", "#8b949e", "#3FA9D6"
LEVELS = ["#161b22", "#0b3a52", "#125A80", "#2b85b5", "#3FA9D6"]
FONT = "font-family='Segoe UI, Ubuntu, Helvetica, Arial, sans-serif'"


def gql(query, **variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        body = json.load(r)
    if "errors" in body:
        raise SystemExit(body["errors"])
    return body["data"]


data = gql(
    """query($login: String!) {
      user(login: $login) {
        followers { totalCount }
        contributionsCollection {
          totalCommitContributions totalPullRequestContributions totalIssueContributions
          contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
        }
        repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
          nodes {
            stargazerCount
            languages(first: 10, orderBy: {field: SIZE, direction: DESC}) { edges { size node { name color } } }
          }
        }
      }
    }""",
    login=LOGIN,
)["user"]

cc = data["contributionsCollection"]
repos = data["repositories"]["nodes"]
stars = sum(r["stargazerCount"] for r in repos)
os.makedirs(OUT, exist_ok=True)


def card(w, h, title, body):
    return (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}' viewBox='0 0 {w} {h}' {FONT}>"
        f"<rect x='0.5' y='0.5' width='{w-1}' height='{h-1}' rx='8' fill='{BG}' stroke='{BORDER}'/>"
        f"<text x='24' y='36' fill='{ACCENT}' font-size='17' font-weight='600'>{escape(title)}</text>"
        f"{body}</svg>"
    )


# Stats card
rows = [
    ("Contributions (last year)", cc["contributionCalendar"]["totalContributions"]),
    ("Commits (last year)", cc["totalCommitContributions"]),
    ("Pull requests (last year)", cc["totalPullRequestContributions"]),
    ("Stars on public repos", stars),
    ("Public repositories", len(repos)),
]
body = "".join(
    f"<text x='24' y='{72 + i*24}' fill='{TEXT}' font-size='14'>{escape(k)}</text>"
    f"<text x='400' y='{72 + i*24}' fill='{TEXT}' font-size='14' font-weight='600' text-anchor='end'>{v:,}</text>"
    for i, (k, v) in enumerate(rows)
)
open(f"{OUT}/stats.svg", "w", encoding="utf-8").write(card(424, 190, "GitHub stats", body))

# Languages card (by bytes, public non-fork repos)
sizes, colors = {}, {}
for r in repos:
    for e in r["languages"]["edges"]:
        n = e["node"]["name"]
        if n in {"HTML", "CSS", "Jupyter Notebook", "MDX", "Shell", "PowerShell", "Batchfile"}:
            continue
        sizes[n] = sizes.get(n, 0) + e["size"]
        colors[n] = e["node"]["color"] or MUTED
top = sorted(sizes.items(), key=lambda kv: -kv[1])[:6]
total = sum(v for _, v in top) or 1
bar, x = "", 24.0
for n, v in top:
    w = 376 * v / total
    bar += f"<rect x='{x:.1f}' y='54' width='{w:.1f}' height='8' fill='{colors[n]}'/>"
    x += w
bar = f"<clipPath id='c'><rect x='24' y='54' width='376' height='8' rx='4'/></clipPath><g clip-path='url(#c)'>{bar}</g>"
legend = "".join(
    f"<circle cx='{30 + (i % 2)*190}' cy='{88 + (i // 2)*26}' r='5' fill='{colors[n]}'/>"
    f"<text x='{42 + (i % 2)*190}' y='{93 + (i // 2)*26}' fill='{TEXT}' font-size='13'>{escape(n)} "
    f"<tspan fill='{MUTED}'>{100*v/total:.1f}%</tspan></text>"
    for i, (n, v) in enumerate(top)
)
open(f"{OUT}/languages.svg", "w", encoding="utf-8").write(card(424, 190, "Most used languages", bar + legend))

# Contribution heatmap (last year)
weeks = cc["contributionCalendar"]["weeks"]
cell, gap, left, topy = 11, 3, 24, 70
mx = max((d["contributionCount"] for w in weeks for d in w["contributionDays"]), default=0) or 1


def level(c):
    if c == 0:
        return 0
    return min(4, 1 + int(4 * (c - 1) / mx))


cells, months, last_month = "", "", None
for wi, w in enumerate(weeks):
    for d in w["contributionDays"]:
        day = dt.date.fromisoformat(d["date"])
        y = topy + ((day.weekday() + 1) % 7) * (cell + gap)
        xx = left + wi * (cell + gap)
        c = d["contributionCount"]
        cells += (f"<rect x='{xx}' y='{y}' width='{cell}' height='{cell}' rx='2' fill='{LEVELS[level(c)]}'>"
                  f"<title>{c} contributions on {d['date']}</title></rect>")
        if day.day <= 7 and day.weekday() == 6 and day.month != last_month:
            months += f"<text x='{xx}' y='{topy - 8}' fill='{MUTED}' font-size='11'>{day:%b}</text>"
            last_month = day.month
width = left * 2 + len(weeks) * (cell + gap) - gap
total = cc["contributionCalendar"]["totalContributions"]
legend = "".join(
    f"<rect x='{width - 24 - (5 - i)*(cell + gap)}' y='{topy + 7*(cell+gap) + 8}' width='{cell}' height='{cell}' rx='2' fill='{c}'/>"
    for i, c in enumerate(LEVELS)
)
note = (f"<text x='{left}' y='{topy + 7*(cell+gap) + 18}' fill='{MUTED}' font-size='12'>"
        f"{total:,} contributions in the last year</text>")
open(f"{OUT}/contributions.svg", "w", encoding="utf-8").write(
    card(width, topy + 7 * (cell + gap) + 34, "Contributions", months + cells + legend + note)
)
print("ok", total, stars, top)
