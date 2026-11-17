"""Discover earned GitHub badges and refresh their verified history.

Uses GitHub's public achievement HTML and authenticated API timestamps. An
incomplete response fails before any generated files are written. Unchanged
badges reuse their verified history and artwork, limiting routine polling to
one public page request.
"""

import argparse
import copy
import json
import os
import re
import subprocess
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import achievements

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "assets/achievements/history.json"
TIERS = ("Base", "Bronze", "Silver", "Gold")
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}


class Node:
    def __init__(self, tag="", attrs=()):
        self.tag = tag
        self.attrs = dict(attrs)
        self.children = []

    def find(self, tag=None, css_class=None):
        for child in self.children:
            if isinstance(child, Node):
                if (tag is None or child.tag == tag) and (
                    css_class is None or css_class in child.attrs.get("class", "").split()
                ):
                    yield child
                yield from child.find(tag, css_class)

    def text(self):
        return " ".join("".join(
            child.text() if isinstance(child, Node) else child for child in self.children
        ).split())


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node()
        self.stack = [self.root]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def first(node, tag=None, css_class=None):
    return next(node.find(tag, css_class), None)


def overview(html, username):
    document = Document(html).root
    badges = []
    seen = set()
    for card in document.find("details"):
        slug = card.attrs.get("data-achievement-slug")
        if not slug:
            continue
        if not re.fullmatch(r"[a-z][a-z0-9-]*", slug) or slug in seen:
            raise ValueError("Malformed or duplicated achievement slug")
        seen.add(slug)
        heading = first(card, "h3")
        image = first(card, "img", "achievement-badge-card")
        dialog = first(card, "details-dialog")
        label = first(card, css_class="achievement-tier-label")
        if not heading or not image or not dialog:
            raise ValueError(f"Incomplete achievement card: {slug}")
        match = re.fullmatch(r"x([1-9][0-9]*)", label.text()) if label else None
        if label and not match:
            raise ValueError(f"Invalid achievement tier count: {slug}")
        detail_url = urljoin("https://github.com", dialog.attrs.get("src", ""))
        expected = f"https://github.com/users/{username}/achievements/{slug}/detail"
        image_url = image.attrs.get("src", "")
        if detail_url != expected or urlparse(image_url).netloc != "github.githubassets.com":
            raise ValueError(f"Unexpected achievement asset or detail URL: {slug}")
        badges.append({"slug": slug, "name": heading.text(), "image_url": image_url,
                       "detail_url": detail_url, "tier_count": int(match[1]) if match else 1})
    if not badges:
        raise ValueError("No earned achievement cards found; retaining the last verified history")
    return badges


class GitHub:
    def __init__(self):
        self.token = os.environ.get("ACHIEVEMENTS_TOKEN") or os.environ.get("GITHUB_TOKEN")

    def fetch(self, url, fragment=False):
        headers = {"User-Agent": "Antech-achievement-history",
                   "Accept": "text/fragment+html" if fragment else "text/html"}
        if fragment:
            headers["X-Requested-With"] = "XMLHttpRequest"
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()

    def graphql(self, query, variables):
        payload = json.dumps({"query": query, "variables": variables})
        if not self.token:
            # Optional local CLI auth; never read or print a token ourselves.
            result = subprocess.run(["gh", "api", "graphql", "--input", "-"],
                                    input=payload, text=True, capture_output=True, check=True)
            result = json.loads(result.stdout)
        else:
            request = urllib.request.Request("https://api.github.com/graphql", data=payload.encode(),
                headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json",
                         "User-Agent": "Antech-achievement-history"})
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.load(response)
        if result.get("errors"):
            raise ValueError("GitHub could not verify a milestone timestamp")
        return result["data"]

    def activity_date(self, source):
        parsed = urlparse(source)
        match = re.fullmatch(r"/([^/]+)/([^/]+)/(pull|issues|discussions)/(\d+)", parsed.path)
        if parsed.netloc != "github.com" or not match:
            return None
        owner, name, kind, number = match.groups()
        field, timestamp = {"pull": ("pullRequest", "mergedAt"),
                            "issues": ("issue", "closedAt"),
                            "discussions": ("discussion", "answerChosenAt")}[kind]
        extra = " answer { url }" if kind == "discussions" else ""
        query = ("query($owner:String!,$name:String!,$number:Int!){"
                 "repository(owner:$owner,name:$name){"
                 f"{field}(number:$number){{{timestamp}{extra}}}" + "}}")
        data = self.graphql(query, {"owner": owner, "name": name, "number": int(number)})
        activity = (data.get("repository") or {}).get(field) or {}
        if kind == "discussions":
            # The answer may have changed since the badge was awarded.
            if (activity.get("answer") or {}).get("url") != source:
                return None
        return activity.get(timestamp)


def milestone(slug, index, label):
    if slug == "pair-extraordinaire":
        thresholds = (1, 10, 24, 48)
        if index < len(thresholds):
            count = thresholds[index]
            return f"{count} coauthored merged {'PR' if count == 1 else 'PRs'}"
    match = re.fullmatch(r"(\d+)(?:st|nd|rd|th) (pull request merged|accepted answer)", label)
    if match:
        return f"{match[1]} {'merged pull requests' if match[2] == 'pull request merged' else 'accepted answers'}"
    return label


def badge_history(card, html, previous, github, username):
    document = Document(html).root
    first_time = first(document, "relative-time")
    rows = list(document.find(css_class="achievement-history-tier"))
    images = list(document.find("img", "tier-badge"))
    if not first_time or not images or len(images) != card["tier_count"]:
        raise ValueError(f"Incomplete badge detail: {card['slug']}")
    if rows and len(rows) != card["tier_count"]:
        raise ValueError(f"Incomplete tier history: {card['slug']}")
    if not rows and card["tier_count"] != 1:
        raise ValueError(f"Missing tier history: {card['slug']}")
    old_history = previous.get("history", []) if previous else []
    history = []
    for index in range(card["tier_count"]):
        row = rows[index] if rows else document
        link = first(row, "a") if rows else None
        label = first(row, "span") if rows else None
        source = urljoin("https://github.com", link.attrs["href"]) if link else (
            f"https://github.com/{username}?achievement={card['slug']}&tab=achievements")
        text = milestone(card["slug"], index, label.text() if label else "Achievement earned")
        tier = TIERS[index] if index < len(TIERS) else f"Tier {index + 1}"
        old = next((item for item in old_history if item["tier"] == tier and item["source"] == source), None)
        row_time = first(row, "relative-time") if rows else None
        if index == 0:
            timestamp, basis = first_time.attrs.get("datetime"), "github_unlock"
        elif row_time:
            timestamp, basis = row_time.attrs.get("datetime"), "github_tier_unlock"
        elif old and old.get("at"):
            timestamp, basis = old["at"], old["date_basis"]
        else:
            timestamp = github.activity_date(source)
            basis = "milestone_activity" if timestamp else "unavailable"
        if index == 0 and not timestamp:
            raise ValueError(f"Missing base unlock timestamp: {card['slug']}")
        if timestamp:
            achievements.date_label(timestamp)
        history.append({"tier": tier, "at": timestamp, "date_basis": basis,
                        "milestone": text, "source": source})
    return {"slug": card["slug"], "name": card["name"], "badge_image_url": card["image_url"],
            "badge_image": f"assets/achievements/{card['slug']}.png", "history": history}


def collect(previous, github, force=False):
    username = previous["username"]
    cards = overview(github.fetch(f"https://github.com/{username}?tab=achievements").decode(), username)
    old_badges = {badge["slug"]: badge for badge in previous["badges"]}
    if not old_badges.keys() <= {card["slug"] for card in cards}:
        raise ValueError("GitHub returned fewer badges; retaining the last verified history")
    badges, images = [], {}
    for card in cards:
        old = old_badges.get(card["slug"])
        if old and card["tier_count"] < len(old["history"]):
            raise ValueError(f"GitHub returned fewer tiers for {card['slug']}")
        unchanged = old and old["name"] == card["name"] and len(old["history"]) == card["tier_count"] and (
            old["badge_image_url"] == card["image_url"])
        if unchanged and not force:
            badge = copy.deepcopy(old)
        else:
            detail = github.fetch(card["detail_url"], fragment=True).decode()
            badge = badge_history(card, detail, old, github, username)
        if not old or old["badge_image_url"] != card["image_url"] or not (ROOT / badge["badge_image"]).is_file():
            image = github.fetch(card["image_url"])
            if not image.startswith(b"\x89PNG\r\n\x1a\n"):
                raise ValueError(f"Invalid badge artwork: {card['slug']}")
            images[badge["slug"]] = image
        badges.append(badge)
    data = copy.deepcopy(previous)
    # Date-only verification avoids committing on every unchanged poll.
    data.update(badges=badges, verified_on=datetime.now(achievements.EAT).date().isoformat(),
                automatic_refresh=True)
    return data, images


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Recheck all badge histories")
    parser.add_argument("--dry-run", action="store_true", help="Verify live data without writing files")
    args = parser.parse_args()
    previous = json.loads(STATE.read_text(encoding="utf-8"))
    data, images = collect(previous, GitHub(), force=args.force)
    readme_path = ROOT / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    achievements.validate_markers(readme)
    # Prepare every card before committing the refresh to disk.
    cards = {badge["slug"]: achievements.render_card(badge, images.get(badge["slug"]))
             for badge in data["badges"]}
    section = achievements.render_section(data)
    if args.dry_run:
        print(f"Verified {len(cards)} live badges and {sum(len(b['history']) for b in data['badges'])} earned tiers; no files written")
        return
    for slug, image in images.items():
        (ROOT / f"assets/achievements/{slug}.png").write_bytes(image)
    for slug, svg in cards.items():
        (ROOT / f"assets/achievements/{slug}.svg").write_text(svg, encoding="utf-8", newline="\n")
    start, end = readme.index(achievements.BEGIN), readme.index(achievements.END) + len(achievements.END)
    readme_path.write_text(readme[:start] + section + readme[end:], encoding="utf-8", newline="\n")
    STATE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"Refreshed {len(cards)} badges; {sum(len(b['history']) for b in data['badges'])} earned tiers")


if __name__ == "__main__":
    main()
