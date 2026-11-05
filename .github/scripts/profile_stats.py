import json
import os
from collections import Counter
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from urllib.request import Request, urlopen

OWNER = os.environ["PROFILE_OWNER"]
TOKEN = os.environ["GH_TOKEN"]
OUT = Path("dist")
OUT.mkdir(exist_ok=True)

def api(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    request = Request("https://api.github.com/" + path, data=data, headers={
        "Authorization": "Bearer " + TOKEN,
        "Accept": "application/vnd.github+json",
        "User-Agent": "profile-visuals",
        "Content-Type": "application/json",
    })
    with urlopen(request, timeout=45) as response:
        result = json.load(response)
    if isinstance(result, dict) and result.get("errors"):
        raise RuntimeError(result["errors"])
    return result

def svg(width, height, title, body, description):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">'
            f'<title>{escape(title)}</title><desc>{escape(description)}</desc>'
            '<rect width="100%" height="100%" rx="14" fill="#0d1117" stroke="#30363d"/>'
            '<g font-family="Segoe UI,Arial,sans-serif">'
            f'<text x="24" y="35" fill="#34d399" font-size="19" font-weight="600">{escape(title)}</text>'
            + body + '</g></svg>')

repos = []
page = 1
while True:
    batch = api(f"users/{OWNER}/repos?per_page=100&page={page}&type=owner")
    repos.extend(r for r in batch if not r.get("private"))
    if len(batch) < 100:
        break
    page += 1
profile = api(f"users/{OWNER}")
owned = [r for r in repos if not r["fork"]]
language_bytes = Counter()
for repo in owned:
    if repo["size"]:
        language_bytes.update(api(f"repos/{OWNER}/{repo['name']}/languages"))

query = """query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount weekday } }
      }
    }
  }
}"""
calendar = api("graphql", {"query": query, "variables": {"login": OWNER}})["data"]["user"]["contributionsCollection"]["contributionCalendar"]
rows = [
    ("Public repositories", len(repos)),
    ("Stars across public repositories", sum(r["stargazers_count"] for r in repos)),
    ("Followers", profile["followers"]),
    ("Contributions in the last year", calendar["totalContributions"]),
]
body = ""
for i, (label, value) in enumerate(rows):
    y = 73 + i * 30
    body += f'<text x="24" y="{y}" fill="#c9d1d9" font-size="14">{escape(label)}</text>'
    body += f'<text x="420" y="{y}" text-anchor="end" fill="#6ee7b7" font-size="16" font-weight="600">{value:,}</text>'
stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
body += f'<text x="24" y="211" fill="#8b949e" font-size="11">Updated {stamp} UTC</text>'
(OUT / "stats.svg").write_text(svg(450, 230, "GitHub at a glance", body, "Public repository statistics and yearly contribution count"), encoding="utf-8")

top = language_bytes.most_common(6)
total = sum(language_bytes.values()) or 1
body = ""
colors = ["#34d399", "#38bdf8", "#c084fc", "#fb923c", "#f472b6", "#facc15"]
for i, (language, size) in enumerate(top):
    y = 66 + i * 25
    pct = size * 100 / total
    body += f'<circle cx="28" cy="{y-4}" r="4" fill="{colors[i]}"/>'
    body += f'<text x="40" y="{y}" fill="#c9d1d9" font-size="13">{escape(language)}</text>'
    body += f'<rect x="170" y="{y-10}" width="170" height="8" rx="4" fill="#21262d"/>'
    body += f'<rect x="170" y="{y-10}" width="{170*pct/100:.1f}" height="8" rx="4" fill="{colors[i]}"/>'
    body += f'<text x="420" y="{y}" text-anchor="end" fill="#c9d1d9" font-size="12">{pct:.1f}%</text>'
body += '<text x="24" y="222" fill="#8b949e" font-size="10">By code bytes in public, non-fork repositories; excludes notebooks.</text>'
(OUT / "languages.svg").write_text(svg(450, 240, "Languages in public projects", body, "Language percentages by GitHub code bytes; not skill proficiency"), encoding="utf-8")

weeks = calendar["weeks"]
body = ""
palette = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
for x, week in enumerate(weeks):
    for day in week["contributionDays"]:
        count = day["contributionCount"]
        level = 0 if count == 0 else 1 if count < 3 else 2 if count < 6 else 3 if count < 10 else 4
        px, py = 35 + x * 15, 65 + day["weekday"] * 15
        body += f'<rect x="{px}" y="{py}" width="11" height="11" rx="2" fill="{palette[level]}"><title>{day["date"]}: {count} contributions</title></rect>'
body += f'<text x="35" y="200" fill="#c9d1d9" font-size="13">{calendar["totalContributions"]:,} contributions in the last year</text>'
body += f'<text x="35" y="222" fill="#8b949e" font-size="11">Updated {stamp} UTC · Activity from GitHub contribution calendar</text>'
(OUT / "activity.svg").write_text(svg(880, 245, "Contribution activity", body, "GitHub contribution calendar for the past year"), encoding="utf-8")


# Build an all-time streak card from yearly contribution calendars.
from datetime import date, timedelta

year_query = """query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}"""
today = datetime.now(timezone.utc).date()
days = {}
for year in range(int(profile["created_at"][:4]), today.year + 1):
    start = f"{year}-01-01T00:00:00Z"
    end = f"{year}-12-31T23:59:59Z" if year < today.year else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cal = api("graphql", {"query": year_query, "variables": {"login": OWNER, "from": start, "to": end}})["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    for week in cal["weeks"]:
        for day in week["contributionDays"]:
            dt = date.fromisoformat(day["date"])
            if dt.year == year and dt <= today:
                days[dt] = day["contributionCount"]

best = run = 0
best_start = best_end = run_start = None
previous = None
for dt in sorted(days):
    if days[dt] > 0:
        if previous is not None and dt == previous + timedelta(days=1):
            run += 1
        else:
            run = 1
            run_start = dt
        previous = dt
        if run > best:
            best, best_start, best_end = run, run_start, dt
    else:
        run = 0
        previous = None

anchor = today if days.get(today, 0) else today - timedelta(days=1)
current = 0
cursor = anchor
while days.get(cursor, 0) > 0:
    current += 1
    cursor -= timedelta(days=1)

def date_label(dt):
    return dt.strftime("%b %d, %Y") if dt else "No streak yet"

current_range = (date_label(cursor + timedelta(days=1)) + " - " + date_label(anchor)) if current else "Start with a contribution today"
best_range = (date_label(best_start) + " - " + date_label(best_end)) if best else "No streak yet"
total = sum(days.values())
joined = date_label(date.fromisoformat(profile["created_at"][:10]))
body = '<path d="M285 32V190M595 32V190" stroke="#484154"/>'
body += '<circle cx="440" cy="79" r="43" fill="none" stroke="#a879ff" stroke-width="5"/>'
for x, number, label, detail in [
    (148, total, "Total Contributions", joined + " - Present"),
    (440, current, "Current Streak", current_range),
    (732, best, "Longest Streak", best_range),
]:
    number_color = "#ffbd70" if x == 440 else "#a879ff"
    body += f'<text x="{x}" y="90" text-anchor="middle" fill="{number_color}" font-size="32" font-weight="700">{number:,}</text>'
    body += f'<text x="{x}" y="153" text-anchor="middle" fill="{number_color}" font-size="16" font-weight="600">{label}</text>'
    body += f'<text x="{x}" y="181" text-anchor="middle" fill="#64ffda" font-size="11">{escape(detail)}</text>'
body += f'<text x="440" y="220" text-anchor="middle" fill="#8b949e" font-size="10">GitHub contribution calendar · UTC · Updated {stamp}</text>'
card = ('<svg xmlns="http://www.w3.org/2000/svg" width="880" height="240" viewBox="0 0 880 240" role="img">'
        '<title>GitHub contribution streaks</title>'
        '<desc>All-time contribution total, current streak and longest streak, measured by UTC calendar days.</desc>'
        '<rect x="1" y="1" width="878" height="238" rx="10" fill="#14121b" stroke="#a879ff"/>'
        '<g font-family="Segoe UI,Arial,sans-serif">' + body + '</g></svg>')
(OUT / "streak.svg").write_text(card, encoding="utf-8")
