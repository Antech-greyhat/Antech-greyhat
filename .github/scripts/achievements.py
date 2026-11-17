"""Render the verified badge history, offline, using only the standard library.

Edit assets/achievements/history.json after checking GitHub's badge history,
then run this script. Base dates are GitHub unlocks; later dates are the linked
milestone activity, because GitHub does not publish each tier's unlock time.
"""

import base64
import json
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BEGIN = "<!-- BEGIN GITHUB ACHIEVEMENTS -->"
END = "<!-- END GITHUB ACHIEVEMENTS -->"
EAT = timezone(timedelta(hours=3))


def date_label(timestamp):
    value = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("Achievement timestamps must include a timezone")
    return value.astimezone(EAT).strftime("%d %b %Y")


def render_card(badge):
    history = badge["history"]
    latest = history[-1]
    name = escape(badge["name"])
    tier = latest["tier"].upper()
    status = f"{tier} / x{len(history)}" if len(history) > 1 else "UNLOCKED"
    image_path = ROOT / badge["badge_image"]
    image_bytes = image_path.read_bytes()
    if not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError(f"Expected a PNG badge image: {image_path}")
    image = base64.b64encode(image_bytes).decode("ascii")
    accessible = escape("; ".join(
        f"{item['tier']} {'unlocked' if index == 0 else 'milestone'} "
        f"on {date_label(item['at'])}: {item['milestone']}"
        for index, item in enumerate(history)
    ), quote=True)
    rows = []
    for index, item in enumerate(history):
        y = 130 + index * 47
        is_latest = index == len(history) - 1
        label = f"{item['tier']} {'unlocked' if index == 0 else 'milestone'}"
        rows.append(
            f'<circle cx="27" cy="{y - 4}" r="4" class="'
            f'{"current" if is_latest else "dot"}"/>\n'
            f'<text x="44" y="{y}" class="label">{escape(label)}</text>\n'
            f'<text x="340" y="{y}" text-anchor="end" class="'
            f'{"date latest" if is_latest else "date"}">{date_label(item["at"])}</text>\n'
            f'<text x="44" y="{y + 18}" class="muted">{escape(item["milestone"])}</text>'
        )
    line = (
        f'<path d="M27 126 V{126 + (len(history) - 1) * 47}" stroke="#1b6533"/>'
        if len(history) > 1 else ""
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 360 284" width="360" height="284" role="img" aria-label="{name}: {accessible}. Dates in EAT, UTC+3.">
<title>{name} achievement history</title>
<desc>{accessible}. Base dates are GitHub unlock dates; later dates are milestone activity dates.</desc>
<style>
text{{font-family:Consolas,"DejaVu Sans Mono","Liberation Mono","Courier New",monospace}}
.name{{fill:#d8ffe4;font-size:17px;font-weight:700}}
.status{{fill:#00ff41;font-size:12px;font-weight:700;letter-spacing:1px}}
.label{{fill:#b6ffcb;font-size:13px}}.date{{fill:#b6ffcb;font-size:13px;font-weight:700}}
.latest{{fill:#00ff41}}.muted{{fill:#86b596;font-size:11px}}
.dot{{fill:#000;stroke:#00ff41;stroke-width:1.5}}.current{{fill:#00ff41}}
</style>
<rect x="1" y="1" width="358" height="282" rx="6" fill="#000" stroke="#00ff41"/>
<image x="14" y="14" width="84" height="84" href="data:image/png;base64,{image}"/>
<text x="110" y="45" class="name">{name}</text>
<text x="110" y="68" class="status">{status}</text>
<path d="M20 106 H340" stroke="#1b6533"/>
{line}
{chr(10).join(rows)}
<path d="M20 252 H340" stroke="#1b6533"/>
<text x="20" y="270" class="muted">[+] dates: EAT (UTC+3)</text>
</svg>
'''


def render_section(data):
    user = data["username"]
    lines = [
        BEGIN,
        '<div align="center">',
        '',
        '<h2 id="github-achievements"><img src="./assets/sections/achievements.svg" alt="GitHub Achievements"/></h2>',
        '',
    ]
    card_links = []
    for badge in data["badges"]:
        url = f"https://github.com/{user}?achievement={badge['slug']}&amp;tab=achievements"
        text = "; ".join(
            f"{item['tier']} {'unlocked' if index == 0 else 'milestone'}: "
            f"{date_label(item['at'])} ({item['milestone']})"
            for index, item in enumerate(badge["history"])
        )
        alt = escape(f"{badge['name']}. {text}. Dates in EAT (UTC+3).", quote=True)
        card_links.append(
            f'<a href="{url}"><img src="./assets/achievements/{badge["slug"]}.svg" '
            f'width="360" alt="{alt}"/></a>'
        )
    for index in range(0, len(card_links), 2):
        lines.append(f'<p>{" ".join(card_links[index:index + 2])}</p>')
    lines.extend([
        '',
        f'<p><sub>Verified {date_label(data["verified_on"] + "T00:00:00+03:00")} · Dates in EAT (UTC+3).<br/>Base dates are GitHub unlock dates; later tiers show the linked milestone activity date.</sub></p>',
        '',
        '</div>',
        '',
        '<details>',
        '<summary>Badge history and source links</summary>',
        '',
        '| Badge | Tier | Date (EAT) | Milestone | Source |',
        '| :--- | :--- | :--- | :--- | :--- |',
    ])
    for badge in data["badges"]:
        for index, item in enumerate(badge["history"]):
            basis = "unlocked" if index == 0 else "milestone"
            lines.append(
                f'| {badge["name"]} | {item["tier"]} {basis} | {date_label(item["at"])} | '
                f'{item["milestone"]} | [View activity]({item["source"]}) |'
            )
    lines.extend(['', '</details>', END])
    return "\n".join(lines)


def main():
    data = json.loads((ROOT / "assets/achievements/history.json").read_text(encoding="utf-8"))
    readme_path = ROOT / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    if readme.count(BEGIN) != 1 or readme.count(END) != 1 or readme.index(BEGIN) >= readme.index(END):
        raise ValueError("README must have exactly one ordered pair of achievement markers")
    cards = {}
    for badge in data["badges"]:
        history = badge["history"]
        if not history or len(history) > 4:
            raise ValueError("Badge history must contain one to four earned tiers")
        for index, item in enumerate(history):
            expected = "github_unlock" if index == 0 else "milestone_activity"
            if item["date_basis"] != expected:
                raise ValueError("Keep GitHub unlocks separate from milestone activity dates")
        cards[badge["slug"]] = render_card(badge)
    section = render_section(data)
    start = readme.index(BEGIN)
    end = readme.index(END) + len(END)
    for slug, svg in cards.items():
        (ROOT / f"assets/achievements/{slug}.svg").write_text(svg, encoding="utf-8", newline="\n")
    readme_path.write_text(readme[:start] + section + readme[end:], encoding="utf-8", newline="\n")
    print(f"Rendered {len(cards)} badges and {sum(len(b['history']) for b in data['badges'])} earned tiers")


if __name__ == "__main__":
    main()
