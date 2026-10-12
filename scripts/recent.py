#!/usr/bin/env python3
"""Rewrite the block between <!-- recent:start --> and <!-- recent:end --> in README.md
with my five most recently pushed public repositories. Run daily by
.github/workflows/recent.yml; GITHUB_TOKEN is optional locally."""
import datetime
import json
import os
import re
import urllib.request
from pathlib import Path

USER = "Jakhangir18"
SKIP = {USER}  # the profile repository itself


def repos():
    req = urllib.request.Request(
        f"https://api.github.com/users/{USER}/repos?sort=pushed&per_page=20&type=owner",
        headers={"Accept": "application/vnd.github+json", "User-Agent": USER})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def block(items):
    rows = []
    for r in items:
        day = datetime.date.fromisoformat(r["pushed_at"][:10]).strftime("%b %-d, %Y")
        desc = (r.get("description") or "").replace("|", "/")
        rows.append(f"| [{r['name']}]({r['html_url']}) | {desc} | {day} |")
    return "| Repository | What it is | Last push |\n|---|---|---|\n" + "\n".join(rows)


def main():
    items = [r for r in repos() if not r["fork"] and not r["private"] and r["name"] not in SKIP][:5]
    readme = Path("README.md")
    text = readme.read_text()
    new = re.sub(r"(<!-- recent:start -->\n).*?(<!-- recent:end -->)",
                 lambda m: m.group(1) + block(items) + "\n" + m.group(2), text, flags=re.S)
    if new != text:
        readme.write_text(new)
        print("README updated")


if __name__ == "__main__":
    main()
