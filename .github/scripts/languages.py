"""Build assets/languages.svg: a terminal-style card of the owner's languages.

Uses only the standard library. Any API error stops the script before the card
is written, so a failed run keeps the last good card.
"""

import json
import math
import os
import urllib.request
from html import escape

USER = os.environ.get("USERNAME", "")
LANGS_TOKEN = os.environ.get("LANGS_TOKEN")
TOKEN = LANGS_TOKEN or os.environ.get("GITHUB_TOKEN")
MAX_ROWS = 8
SEGMENTS = 25


def api(path):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "language-card",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    request = urllib.request.Request(f"https://api.github.com{path}", headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def list_repos():
    # LANGS_TOKEN (optional) can see private repos; GITHUB_TOKEN sees public ones.
    base = "/user/repos?affiliation=owner" if LANGS_TOKEN else f"/users/{USER}/repos?type=owner"
    repos = []
    page = 1
    while True:
        batch = api(f"{base}&per_page=100&page={page}")
        repos.extend(batch)
        if len(batch) < 100:
            return [repo for repo in repos if not repo["fork"]]
        page += 1


def esc(text):
    return escape(text, quote=False)


def render(rows, lang_count, repo_count):
    row_h = 24
    top = 62
    height = top + len(rows) * row_h + 40
    body = ""
    for i, (name, pct) in enumerate(rows):
        y = top + i * row_h
        lit = max(1, math.floor(pct / 100 * SEGMENTS + 0.5))
        segs = ""
        for s in range(SEGMENTS):
            on = s < lit
            delay = f' style="animation-delay:{i * 80 + s * 25}ms"' if on else ""
            segs += (
                f'<rect x="{165 + s * 10}" y="{y - 12}" width="8" height="14" '
                f'class="{"on" if on else "off"}"{delay}/>'
            )
        body += (
            f'<text class="l" x="20" y="{y}">{esc(name)}</text>{segs}'
            f'<text class="p" x="475" y="{y}" text-anchor="end">{pct:.1f}%</text>\n'
        )
    foot_y = top + len(rows) * row_h + 16
    label = esc(", ".join(f"{name} {pct:.1f}%" for name, pct in rows))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 495 {height}" width="495" height="{height}" role="img" aria-label="Most used languages: {label}">
<style>
text{{font-family:Consolas,"DejaVu Sans Mono","Liberation Mono","Courier New",monospace;font-size:14px;font-weight:700}}
.t{{fill:#00ff41;font-size:15px}}.l{{fill:#b6ffcb}}.p{{fill:#00ff41}}.f{{fill:#00ff41;fill-opacity:.8;font-size:13px}}
.on{{fill:#00ff41;animation:lit .15s linear both}}.off{{fill:#00ff41;fill-opacity:.12}}
@keyframes lit{{from{{opacity:0}}}}
@media (prefers-reduced-motion:reduce){{.on{{animation:none}}}}
</style>
<rect x="1" y="1" width="493" height="{height - 2}" rx="6" fill="#000" stroke="#00ff41"/>
<text class="t" x="20" y="30">root@antech:~# ./scan --languages</text>
{body}<text class="f" x="20" y="{foot_y}">[+] scan complete: {lang_count} languages across {repo_count} repos</text>
</svg>
"""


def main():
    repos = list_repos()
    totals = {}
    for repo in repos:
        for name, size in api(f"/repos/{repo['full_name']}/languages").items():
            totals[name] = totals.get(name, 0) + size

    total = sum(totals.values())
    if not total:
        raise SystemExit("no language data found")

    top = sorted(totals.items(), key=lambda item: item[1], reverse=True)[:MAX_ROWS]
    rows = [(name, size / total * 100) for name, size in top]
    rows = [(name, pct) for name, pct in rows if pct >= 0.05]

    with open("assets/languages.svg", "w", encoding="utf-8", newline="\n") as card:
        card.write(render(rows, len(totals), len(repos)))
    for name, pct in rows:
        print(f"{name} {pct:.1f}%")


if __name__ == "__main__":
    main()
