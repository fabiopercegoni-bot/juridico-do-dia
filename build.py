"""Build the legal news aggregator static site.

Reads feeds from feeds.json, classifies items by area using keywords.json,
and renders HTML pages into docs/ for GitHub Pages.
"""

import html
import json
import re
import shutil
import sys
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "docs"
TEMPLATES_DIR = ROOT / "templates"
STATIC_DIR = ROOT / "static"

WINDOW_DAYS = 7
MIN_SCORE = 1
USER_AGENT = "Mozilla/5.0 (compatible; JuridicoDoDia/1.0; +https://github.com/)"

MONTHS_PT = [
    "", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]

BR_TZ = timezone(timedelta(hours=-3))


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.lower()


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    # Strip WordPress-style RSS boilerplate ("O post X apareceu primeiro em Y")
    text = re.sub(r"\[?\.{2,}\]?\s*O\s+post\s+.+$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"O\s+post\s+.+\s+(apareceu primeiro em|foi publicado primeiro em).+$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def is_redundant_description(title: str, description: str) -> bool:
    """True when the description is just a repeat of the title (common in
    Google News feeds where summary == title + source name)."""
    if not description:
        return True
    t = normalize(title)
    d = normalize(description)
    # Identical, or description is a prefix of title (or vice versa)
    if t == d or d.startswith(t) or t.startswith(d):
        return True
    # Description is mostly the title (>80% overlap)
    if len(d) < len(t) * 1.3 and t[:60] in d:
        return True
    return False


def clean_gnews_title(title: str) -> str:
    """Google News appends ' - Source Name' to every title. Strip it for cleaner display."""
    # Common patterns: " - Migalhas", " - stf noticias", " - Superior Tribunal de Justiça"
    return re.sub(r"\s+-\s+[^-]{2,60}$", "", title).strip()


def truncate(text: str, limit: int = 360) -> str:
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0]
    return cut + "…"


def load_config():
    feeds = json.loads((ROOT / "feeds.json").read_text(encoding="utf-8"))
    keywords = json.loads((ROOT / "keywords.json").read_text(encoding="utf-8"))
    return feeds["sources"], keywords["areas"]


def fetch_feed(source: dict) -> list[dict]:
    parsed = feedparser.parse(source["url"], agent=USER_AGENT)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(f"feedparser error: {parsed.bozo_exception}")

    items = []
    for entry in parsed.entries:
        published = None
        for key in ("published_parsed", "updated_parsed"):
            tm = entry.get(key)
            if tm:
                published = datetime(*tm[:6], tzinfo=timezone.utc)
                break
        if not published:
            continue

        raw_title = (entry.get("title") or "").strip()
        if not raw_title:
            continue
        raw_title = re.sub(r"\s+", " ", raw_title)
        title = clean_gnews_title(raw_title)

        link = entry.get("link") or ""
        description = truncate(strip_html(entry.get("summary", "")))
        if is_redundant_description(title, description):
            description = ""

        items.append({
            "title": title,
            "link": link,
            "description": description,
            "published": published,
            "source_id": source["id"],
            "source_short": source["short"],
            "source_name": source["name"],
        })
    return items


def score_item(item: dict, area: dict) -> tuple[int, list[str]]:
    """Score how well an item matches an area.

    Strong keywords add 3 points, regular keywords add 1.
    Duplicates that normalize to the same form (e.g. "ICMS" and "icms",
    or "tributário" and "tributario") are counted only once, avoiding
    inflated scores from accented/unaccented variants in keywords.json.
    """
    text = normalize(item["title"] + " " + item["description"])
    score = 0
    matched: list[str] = []
    seen: set[str] = set()
    for kw in area.get("strong_keywords", []):
        kw_norm = normalize(kw)
        if kw_norm in seen:
            continue
        seen.add(kw_norm)
        pattern = r"(?:^|[^a-z0-9])" + re.escape(kw_norm) + r"(?:$|[^a-z0-9])"
        if re.search(pattern, text):
            score += 3
            matched.append(kw)
    for kw in area.get("keywords", []):
        kw_norm = normalize(kw)
        if kw_norm in seen:
            continue
        seen.add(kw_norm)
        pattern = r"(?:^|[^a-z0-9])" + re.escape(kw_norm) + r"(?:$|[^a-z0-9])"
        if re.search(pattern, text):
            score += 1
            matched.append(kw)
    return score, matched


def classify(items: list[dict], areas: list[dict]) -> dict[str, list[dict]]:
    by_area: dict[str, list[dict]] = {a["id"]: [] for a in areas}
    for item in items:
        best_id = None
        best_score = MIN_SCORE - 1
        for area in areas:
            score, matched = score_item(item, area)
            if score > best_score:
                best_score = score
                best_id = area["id"]
                item["_matched"] = matched
        if best_id:
            item["score"] = best_score
            by_area[best_id].append(item)
    return by_area


def dedupe(items: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        key = normalize(item["title"])[:90]
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def relative_date_pt(dt: datetime, now: datetime) -> str:
    dt_local = dt.astimezone(BR_TZ).date()
    now_local = now.astimezone(BR_TZ).date()
    delta = (now_local - dt_local).days
    if delta == 0:
        return "Hoje"
    if delta == 1:
        return "Ontem"
    if delta < 7:
        return f"Há {delta} dias"
    return f"{dt_local.day}/{dt_local.month:02d}/{dt_local.year}"


def formatted_date_pt(dt: datetime) -> str:
    dt_local = dt.astimezone(BR_TZ)
    return f"{dt_local.day:02d}/{dt_local.month:02d}/{dt_local.year} · {dt_local.strftime('%H:%M')}"


def long_date_pt(dt: datetime) -> str:
    dt_local = dt.astimezone(BR_TZ)
    return f"{dt_local.day} de {MONTHS_PT[dt_local.month]} de {dt_local.year}"


def main() -> int:
    sources, areas = load_config()
    print(f"[1/4] Fetching {len(sources)} sources...")
    all_items: list[dict] = []
    for source in sources:
        try:
            items = fetch_feed(source)
            print(f"      {source['short']:<10} {len(items):>3} items")
            all_items.extend(items)
        except Exception as exc:
            print(f"      {source['short']:<10} ERROR: {exc}", file=sys.stderr)

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=WINDOW_DAYS)

    print(f"[2/4] Filtering to last {WINDOW_DAYS} days...")
    recent = [i for i in all_items if i["published"] >= cutoff]
    recent = dedupe(recent)
    print(f"      {len(recent)} items after dedup")

    print(f"[3/4] Classifying into {len(areas)} areas...")
    by_area = classify(recent, areas)
    for area in areas:
        items = by_area[area["id"]]
        items.sort(key=lambda i: i["published"], reverse=True)
        print(f"      {area['name']:<22} {len(items):>3} items")

    print("[4/4] Rendering HTML...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if STATIC_DIR.exists():
        for src in STATIC_DIR.iterdir():
            shutil.copy(src, OUTPUT_DIR / src.name)

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["relative_date"] = lambda dt: relative_date_pt(dt, now)
    env.filters["full_date"] = formatted_date_pt
    env.filters["long_date"] = long_date_pt

    area_summary = []
    for area in areas:
        items = by_area[area["id"]]
        today_count = sum(
            1 for i in items
            if i["published"].astimezone(BR_TZ).date() == now.astimezone(BR_TZ).date()
        )
        area_summary.append({
            "id": area["id"],
            "name": area["name"],
            "description": area["description"],
            "total": len(items),
            "today": today_count,
        })

    common = {
        "updated_at": now,
        "today_long": long_date_pt(now),
        "sources": sources,
        "window_days": WINDOW_DAYS,
    }

    index_html = env.get_template("index.html").render(
        areas=area_summary,
        **common,
    )
    (OUTPUT_DIR / "index.html").write_text(index_html, encoding="utf-8")

    for area in areas:
        html = env.get_template("area.html").render(
            area=area,
            items=by_area[area["id"]],
            all_areas=area_summary,
            **common,
        )
        (OUTPUT_DIR / f"{area['id']}.html").write_text(html, encoding="utf-8")

    print(f"\nDone. Site generated in {OUTPUT_DIR.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
