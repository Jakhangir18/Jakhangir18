import io
import json
import urllib.error

import pytest

from scripts import climate


def test_score_stops_at_each_cap():
    assert climate.score(commits=30, active_days=12, streak=5, public_repos=20) == 100


def test_score_below_the_caps():
    assert climate.score(commits=3, active_days=2, streak=1, public_repos=4) == 19


def test_public_repos_alone_give_at_most_ten():
    assert climate.score(commits=0, active_days=0, streak=0, public_repos=30) == 10


@pytest.mark.parametrize("points, name, mood", [
    (0, "Dead Desert", "fog"), (9.5, "Dead Desert", "fog"),
    (10, "Ice Tundra", "snow"), (24.5, "Ice Tundra", "snow"),
    (25, "Subtropics", "rain"), (44.5, "Subtropics", "rain"),
    (45, "Spring", "wind"), (69.5, "Spring", "wind"),
    (70, "Summer", "sunny"), (100, "Summer", "sunny"),
])
def test_biome_boundaries(points, name, mood):
    assert climate.biome(points) == (name, mood)


def test_longest_streak_ignores_repeats_and_gaps():
    days = ["2026-10-01", "2026-10-02", "2026-10-04", "2026-10-05", "2026-10-06", "2026-10-06"]
    assert climate.longest_streak(days) == 3


def test_longest_streak_crosses_a_month():
    assert climate.longest_streak(["2026-10-01", "2026-09-30"]) == 2


def test_longest_streak_of_nothing():
    assert climate.longest_streak([]) == 0


def test_climate_counts_and_rounds_half_up():
    # 1 commit (2) + 1 day (3) + streak 1 (5) + 1 repo (0.5) = 10.5, shown as 11.
    got = climate.climate(["2026-10-01"], public_repos=1, weeks=[0, 4])
    assert (got.score, got.biome, got.mood) == (11, "Ice Tundra", "snow")
    assert (got.commits, got.active_days, got.streak, got.weeks) == (1, 1, 1, (0, 4))
    assert got.public_repos == 1


def test_climate_counts_every_commit_but_each_day_once():
    got = climate.climate(["2026-10-01", "2026-10-01", "2026-10-03"], public_repos=0, weeks=[])
    assert (got.commits, got.active_days, got.streak, got.score) == (3, 2, 1, 17)


def _commit(date):
    return {"commit": {"author": {"date": date}}}


def _http_error(code):
    return urllib.error.HTTPError("u", code, "x", None, io.BytesIO())  # type: ignore[arg-type]


def test_commit_days_joins_repos_and_skips_empty_and_missing_ones(monkeypatch):
    def fake(url, token, data=None):
        assert token == "t"
        if "/users/" in url:
            return [{"full_name": n} for n in ("me/empty", "me/app", "me/gone", "me/site")]
        if "me/empty" in url:
            raise _http_error(409)
        if "me/gone" in url:
            raise _http_error(404)
        if "me/app" in url:
            return [_commit("2026-10-12T05:33:10Z"), _commit("2026-10-11T23:59:59Z")]
        return [_commit("2026-09-01T00:00:00Z")]

    monkeypatch.setattr(climate, "_get", fake)
    assert climate.commit_days("me", "t") == ["2026-10-12", "2026-10-11", "2026-09-01"]


def test_commit_days_reads_only_the_ten_newest_repos(monkeypatch):
    asked = []

    def fake(url, token, data=None):
        if "/users/" in url:
            return [{"full_name": f"me/r{i}"} for i in range(12)]
        asked.append(url)
        return []

    monkeypatch.setattr(climate, "_get", fake)
    climate.commit_days("me", None)
    assert len(asked) == 10 and "me/r9/" in asked[-1]


def test_commit_days_does_not_hide_a_rate_limit(monkeypatch):
    def fake(url, token, data=None):
        if "/users/" in url:
            return [{"full_name": "me/app"}]
        raise _http_error(403)

    monkeypatch.setattr(climate, "_get", fake)
    with pytest.raises(urllib.error.HTTPError):
        climate.commit_days("me", None)


def _calendar(counts):
    weeks = [{"contributionDays": [{"contributionCount": n}, {"contributionCount": 1}]}
             for n in counts]
    return {"data": {"user": {"contributionsCollection": {"contributionCalendar": {"weeks": weeks}}}}}


def test_weekly_sums_days_and_keeps_the_last_26(monkeypatch):
    sent = {}

    def fake(url, token, data=b"{}"):
        sent.update(json.loads(data), url=url, token=token)
        return _calendar(range(53))

    monkeypatch.setattr(climate, "_get", fake)
    got = climate.weekly("me", "t")
    assert got == tuple(range(28, 54))
    assert sent == {"query": climate.CALENDAR, "variables": {"login": "me"},
                    "url": "https://api.github.com/graphql", "token": "t"}


def test_weekly_accepts_a_calendar_of_exactly_26_weeks(monkeypatch):
    monkeypatch.setattr(climate, "_get", lambda url, token, data=None: _calendar(range(26)))
    assert len(climate.weekly("me", "t")) == 26


def test_weekly_fails_on_a_short_calendar(monkeypatch):
    monkeypatch.setattr(climate, "_get", lambda url, token, data=None: _calendar(range(25)))
    with pytest.raises(RuntimeError, match="25 weeks"):
        climate.weekly("me", "t")


def test_weekly_fails_on_a_graphql_error(monkeypatch):
    monkeypatch.setattr(climate, "_get", lambda url, token, data=None: {"errors": ["bad"]})
    with pytest.raises(RuntimeError, match="bad"):
        climate.weekly("me", "t")
