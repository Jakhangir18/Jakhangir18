"""Score my public commit activity by the rules of commitweather
(github.com/Jakhangir18/commitweather, src/lib/github.ts) and read the weekly
contribution totals of the past six months. Imported by scripts/world.py."""
from __future__ import annotations

import datetime
import json
import math
import urllib.error
import urllib.request
from dataclasses import dataclass

API = "https://api.github.com"
WEEKS = 26  # half a year of trees fits the picture at a readable size
# (score below this, biome, weather); the first match wins. The score never passes 100.
BIOMES = (
    (10, "Dead Desert", "fog"),
    (25, "Ice Tundra", "snow"),
    (45, "Subtropics", "rain"),
    (70, "Spring", "wind"),
    (math.inf, "Summer", "sunny"),
)
CALENDAR = """query($login: String!) { user(login: $login) { contributionsCollection {
  contributionCalendar { weeks { contributionDays { contributionCount } } } } } }"""


@dataclass(frozen=True)
class Climate:
    score: int
    biome: str
    mood: str
    commits: int
    active_days: int
    streak: int
    public_repos: int
    weeks: tuple[int, ...]  # contributions per week, oldest first


def longest_streak(days) -> int:
    """Longest run of consecutive calendar days among ISO dates."""
    best = run = 0
    prev = None
    for day in sorted(datetime.date.fromisoformat(d) for d in set(days)):
        run = run + 1 if prev and (day - prev).days == 1 else 1
        best = max(best, run)
        prev = day
    return best


def score(commits: int, active_days: int, streak: int, public_repos: int) -> float:
    return (min(commits * 2, 40) + min(active_days * 3, 30)
            + min(streak * 5, 20) + min(public_repos * 0.5, 10))


def biome(points: float) -> tuple[str, str]:
    return next((name, mood) for limit, name, mood in BIOMES if points < limit)


def climate(days, public_repos: int, weeks) -> Climate:
    """days: one ISO date per commit, repeats included."""
    days = list(days)
    active = set(days)
    streak = longest_streak(active)
    points = score(len(days), len(active), streak, public_repos)
    name, mood = biome(points)
    # floor(x + 0.5) is JavaScript's Math.round, which the app uses for the shown score.
    return Climate(math.floor(points + 0.5), name, mood, len(days), len(active), streak,
                   public_repos, tuple(weeks))


def _get(url: str, token: str | None, data: bytes | None = None):
    req = urllib.request.Request(url, data=data, headers={
        "Accept": "application/vnd.github+json", "User-Agent": "profile-world"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def commit_days(user: str, token: str | None) -> list[str]:
    """UTC dates of my commits: up to 30 from each of my 10 most recently updated repos."""
    repos = _get(f"{API}/users/{user}/repos?per_page=100&sort=updated", token)[:10]
    days = []
    for repo in repos:
        try:
            commits = _get(f"{API}/repos/{repo['full_name']}/commits?author={user}&per_page=30",
                           token)
        except urllib.error.HTTPError as err:
            if err.code in (404, 409):  # repository gone or empty
                continue
            raise
        days += [c["commit"]["author"]["date"][:10] for c in commits]
    return days


def weekly(user: str, token: str) -> tuple[int, ...]:
    body = json.dumps({"query": CALENDAR, "variables": {"login": user}}).encode()
    reply = _get(f"{API}/graphql", token, body)
    if reply.get("errors"):
        raise RuntimeError(f"contribution calendar: {reply['errors']}")
    weeks = reply["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    totals = tuple(sum(d["contributionCount"] for d in w["contributionDays"]) for w in weeks)
    if len(totals) < WEEKS:
        raise RuntimeError(f"contribution calendar: {len(totals)} weeks, expected {WEEKS}")
    return totals[-WEEKS:]


def read(user: str, token: str) -> Climate:
    days = commit_days(user, token)
    public_repos = _get(f"{API}/users/{user}", token)["public_repos"]
    return climate(days, public_repos, weekly(user, token))
