"""Aggrega i feed elencati in sources.yml e genera i feed RSS in public/.

Uscite:
  public/feed.xml      tutte le fonti
  public/security.xml  solo security advisory e CVE
  public/privacy.xml   solo GDPR e data privacy
  public/index.html    pagina con i link ai feed e lo stato delle fonti
"""

import argparse
import calendar
import html
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from xml.etree import ElementTree as ET

import feedparser
import yaml

USER_AGENT = "feed-rss-personale/1.0 (+https://github.com)"
MAX_AGE_DAYS = 14
MAX_ITEMS = 300
SUMMARY_CHARS = 600

TITLES = {
    "feed": "Feed personale: security e privacy",
    "security": "Feed personale: security advisory e CVE",
    "privacy": "Feed personale: GDPR e data privacy",
}


def load_sources(path):
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    sources = []
    for category, items in data.items():
        for item in items or []:
            sources.append({**item, "category": category})
    return sources


def fetch(source):
    """Scarica e interpreta un feed. Non solleva mai: gli errori finiscono in 'error'."""
    try:
        parsed = feedparser.parse(source["url"], agent=USER_AGENT, request_headers={"Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.5"})
    except Exception as exc:  # feedparser di solito non solleva, ma per sicurezza
        return source, [], f"{type(exc).__name__}: {exc}"
    status = getattr(parsed, "status", None)
    if status and status >= 400:
        return source, [], f"HTTP {status}"
    if not parsed.entries:
        reason = str(parsed.get("bozo_exception", "nessuna voce"))
        return source, [], reason[:200]
    return source, parsed.entries, None


def normalize_link(link):
    parts = urlsplit(link.strip())
    query = "&".join(p for p in parts.query.split("&") if p and not p.startswith("utm_"))
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), query, ""))


def entry_time(entry):
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            return datetime.fromtimestamp(calendar.timegm(value), tz=timezone.utc)
    return None


def strip_tags(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    return " ".join(html.unescape(text).split())


def build_items(results, now):
    items = {}
    cutoff = now.timestamp() - MAX_AGE_DAYS * 86400
    for source, entries, error in results:
        if error:
            continue
        keywords = [k.lower() for k in source.get("include", [])]
        kept = 0
        for entry in entries:
            link = entry.get("link")
            title = strip_tags(entry.get("title", "")).strip()
            if not link or not title:
                continue
            summary = strip_tags(entry.get("summary", ""))
            if keywords and not any(k in f"{title} {summary}".lower() for k in keywords):
                continue
            when = entry_time(entry) or now
            if when.timestamp() < cutoff:
                continue
            key = normalize_link(link)
            if key in items:  # stessa notizia da due fonti: tengo la prima
                continue
            items[key] = {
                "title": title,
                "link": link.strip(),
                "summary": summary[:SUMMARY_CHARS],
                "date": when,
                "source": source["name"],
                "source_url": source["url"],
                "category": source["category"],
                "guid": entry.get("id") or link.strip(),
            }
            kept += 1
            if source.get("max_items") and kept >= source["max_items"]:
                break
    return sorted(items.values(), key=lambda i: i["date"], reverse=True)[:MAX_ITEMS]


def write_rss(path, title, items, site_url, now):
    rss = ET.Element("rss", version="2.0", attrib={"xmlns:atom": "http://www.w3.org/2005/Atom"})
    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = title
    ET.SubElement(channel, "link").text = site_url or "https://example.invalid/"
    ET.SubElement(channel, "description").text = title
    ET.SubElement(channel, "language").text = "it"
    ET.SubElement(channel, "lastBuildDate").text = format_datetime(now)
    if site_url:
        ET.SubElement(channel, "atom:link", href=site_url.rstrip("/") + "/" + path.name, rel="self", type="application/rss+xml")
    for item in items:
        node = ET.SubElement(channel, "item")
        ET.SubElement(node, "title").text = f"[{item['source']}] {item['title']}"
        ET.SubElement(node, "link").text = item["link"]
        ET.SubElement(node, "guid", isPermaLink="false").text = item["guid"]
        ET.SubElement(node, "pubDate").text = format_datetime(item["date"])
        ET.SubElement(node, "category").text = item["category"]
        ET.SubElement(node, "source", url=item["source_url"]).text = item["source"]
        if item["summary"]:
            ET.SubElement(node, "description").text = item["summary"]
    ET.indent(rss)
    path.write_bytes(ET.tostring(rss, encoding="utf-8", xml_declaration=True))


def write_index(path, results, items, now):
    rows = []
    for source, entries, error in sorted(results, key=lambda r: (r[0]["category"], r[0]["name"])):
        count = sum(1 for i in items if i["source"] == source["name"])
        state = f"errore: {html.escape(error)}" if error else f"ok, voci nel feed: {count}"
        rows.append(f"<tr><td>{html.escape(source['category'])}</td><td>{html.escape(source['name'])}</td><td>{state}</td></tr>")
    path.write_text(
        f"""<!doctype html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Feed personale</title>
<link rel="alternate" type="application/rss+xml" title="{TITLES['feed']}" href="feed.xml">
<style>body{{font-family:system-ui,sans-serif;max-width:760px;margin:2rem auto;padding:0 16px;line-height:1.5}}
table{{border-collapse:collapse;width:100%}}td{{border-bottom:1px solid #ddd;padding:4px 8px;font-size:.9rem}}</style></head>
<body><h1>Feed personale</h1>
<ul><li><a href="feed.xml">feed.xml</a>: tutte le fonti</li>
<li><a href="security.xml">security.xml</a>: security advisory e CVE</li>
<li><a href="privacy.xml">privacy.xml</a>: GDPR e data privacy</li></ul>
<p>Aggiornato: {now.strftime('%d/%m/%Y %H:%M')} UTC. Voci: {len(items)}.</p>
<h2>Stato delle fonti</h2><table>{''.join(rows)}</table></body></html>
""",
        encoding="utf-8",
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", default="sources.yml")
    parser.add_argument("--out", default="public")
    parser.add_argument("--site-url", default="")
    args = parser.parse_args()

    sources = load_sources(args.sources)
    started = time.time()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(fetch, sources))

    for source, entries, error in results:
        print(f"{'ERR' if error else 'ok ':3} {source['name']}: {error or f'{len(entries)} voci'}")

    if all(error for _, _, error in results):
        print("Nessuna fonte raggiungibile: non sovrascrivo il feed.", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc)
    items = build_items(results, now)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    write_rss(out / "feed.xml", TITLES["feed"], items, args.site_url, now)
    for category in ("security", "privacy"):
        write_rss(out / f"{category}.xml", TITLES[category], [i for i in items if i["category"] == category], args.site_url, now)
    write_index(out / "index.html", results, items, now)
    print(f"Scritte {len(items)} voci in {out}/ in {time.time() - started:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
