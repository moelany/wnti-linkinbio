#!/usr/bin/env python3
"""
WNTI Link-in-Bio Updater
Fetches the 5 newest articles from the wnti.ch RSS feed and updates index.html.
"""

import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.request import urlopen, Request
from html import escape

RSS_URL = "https://wnti.ch/api/rss-feed"
HTML_FILE = "index.html"
ARTICLE_COUNT = 5  # 1 featured + 4 in list

ARROW_RIGHT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"></path></svg>'
ARROW_CHEVRON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"></path></svg>'
WAVE_SVG = '''<svg class="wave" viewBox="0 0 120 40" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M0 20 Q15 5 30 20 Q45 35 60 20 Q75 5 90 20 Q105 35 120 20" stroke="#FFFFFF" stroke-width="2.5" stroke-opacity="0.25" fill="none"/>
        </svg>'''


def fetch_rss():
    req = Request(RSS_URL, headers={"User-Agent": "WNTI-LinkInBio/1.0"})
    with urlopen(req, timeout=30) as resp:
        return resp.read()


def parse_articles(xml_bytes):
    """Parse RSS feed, return list of article dicts sorted by pubDate desc."""
    ns = {
        "media": "http://search.yahoo.com/mrss/",
        "dc": "http://purl.org/dc/elements/1.1/",
        "content": "http://purl.org/rss/1.0/modules/content/",
    }

    root = ET.fromstring(xml_bytes)
    channel = root.find("channel")
    if channel is None:
        channel = root  # some feeds skip <channel>

    articles = []
    for item in channel.findall("item"):
        def text(tag, default=""):
            el = item.find(tag)
            if el is None:
                # try with dc namespace
                el = item.find(f"dc:{tag}", ns)
            return (el.text or "").strip() if el is not None else default

        title = text("title")
        link = text("link")
        description = text("description")
        pub_date_raw = text("pubDate")
        author = text("author") or text("creator", "") or item.findtext(f"dc:creator", "", ns)

        # Image: try media:content, then media:thumbnail, then enclosure
        image_url = ""
        media_content = item.find("media:content", ns)
        if media_content is not None:
            image_url = media_content.get("url", "")
        if not image_url:
            media_thumb = item.find("media:thumbnail", ns)
            if media_thumb is not None:
                image_url = media_thumb.get("url", "")
        if not image_url:
            enclosure = item.find("enclosure")
            if enclosure is not None and "image" in enclosure.get("type", ""):
                image_url = enclosure.get("url", "")
        if not image_url:
            # Try to find image in description
            img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', description)
            if img_match:
                image_url = img_match.group(1)

        # Clean description of HTML tags
        clean_desc = re.sub(r"<[^>]+>", "", description).strip()
        # Truncate to ~160 chars
        if len(clean_desc) > 180:
            clean_desc = clean_desc[:177].rsplit(" ", 1)[0] + "…"

        # Parse date
        pub_date = None
        for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                    "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"]:
            try:
                pub_date = datetime.strptime(pub_date_raw.strip(), fmt)
                break
            except (ValueError, AttributeError):
                pass

        if title and link:
            articles.append({
                "title": title,
                "link": link,
                "description": clean_desc,
                "image": image_url,
                "author": author,
                "pub_date": pub_date,
                "pub_date_raw": pub_date_raw,
            })

    # Sort by date, newest first
    articles.sort(key=lambda a: a["pub_date"] or datetime.min.replace(tzinfo=None), reverse=True)
    return articles[:ARTICLE_COUNT]


def format_date_de(dt):
    """Format datetime as German date string, e.g. '09. Juni 2026'"""
    if dt is None:
        return ""
    MONTHS = ["Jan.", "Feb.", "März", "Apr.", "Mai", "Juni",
              "Juli", "Aug.", "Sep.", "Okt.", "Nov.", "Dez."]
    return f"{dt.day:02d}. {MONTHS[dt.month - 1]} {dt.year}"


def format_date_short(dt):
    """Format datetime as short German date, e.g. '09. Juni'"""
    if dt is None:
        return ""
    MONTHS = ["Jan.", "Feb.", "März", "Apr.", "Mai", "Juni",
              "Juli", "Aug.", "Sep.", "Okt.", "Nov.", "Dez."]
    return f"{dt.day:02d}. {MONTHS[dt.month - 1]}"


def build_featured(article):
    img_html = ""
    if article["image"]:
        img_html = f'<img src="{escape(article["image"])}" alt="{escape(article["title"])}" loading="eager">'
    else:
        img_html = f'<div class="ph">{WAVE_SVG}</div>'

    meta_parts = []
    if article["pub_date"]:
        meta_parts.append(format_date_de(article["pub_date"]))
    if article["author"]:
        meta_parts.append(escape(article["author"]))
    meta_str = " · ".join(meta_parts)

    desc_html = f'<p class="feat-lead">{escape(article["description"])}</p>\n      ' if article["description"] else ""

    return f'''  <div class="section-label"><span class="pulse"></span> Heute im Fokus</div>

  <a class="featured" href="{escape(article["link"])}" target="_blank" rel="noopener" data-screen-label="Hero-Artikel">
    <div class="feat-media">
      {img_html}
      <span class="feat-flag"><span class="pulse"></span> Neuster Artikel</span>
    </div>
    <div class="feat-body">
      <div class="feat-meta">{meta_str}</div>
      <h2 class="feat-title">{escape(article["title"])}</h2>
      {desc_html}<span class="feat-btn">Artikel lesen {ARROW_RIGHT}</span>
    </div>
  </a>'''


def build_row(article):
    if article["image"]:
        thumb_html = f'<img src="{escape(article["image"])}" alt="{escape(article["title"])}" loading="lazy">'
    else:
        thumb_html = f'<div class="ph">{WAVE_SVG}</div>'

    meta_parts = []
    if article["pub_date"]:
        meta_parts.append(format_date_short(article["pub_date"]))
    if article["author"]:
        meta_parts.append(escape(article["author"]))
    meta_str = " · ".join(meta_parts)

    return f'''    <a class="row" href="{escape(article["link"])}" target="_blank" rel="noopener">
      <div class="row-thumb">
        {thumb_html}
      </div>
      <div class="row-text">
        <div class="row-meta">{meta_str}</div>
        <div class="row-title">{escape(article["title"])}</div>
      </div>
      <span class="row-arrow">{ARROW_CHEVRON}</span>
    </a>'''


def build_article_list(articles):
    rows = "\n\n".join(build_row(a) for a in articles)
    return f'''  <div class="section-label">Das bewegt Winterthur gerade</div>

  <section class="feed">

{rows}

    <a class="all-link" href="https://wnti.ch/" target="_blank" rel="noopener">
      Alle Artikel auf wnti.ch
      {ARROW_RIGHT}
    </a>

  </section>'''


def update_html(html, articles):
    if not articles:
        print("No articles found, skipping update.")
        return html

    featured = articles[0]
    rest = articles[1:]

    new_featured = build_featured(featured)
    new_list = build_article_list(rest)

    # Replace featured section
    html = re.sub(
        r"<!-- FEATURED_ARTICLE_START -->.*?<!-- FEATURED_ARTICLE_END -->",
        f"<!-- FEATURED_ARTICLE_START -->\n{new_featured}\n<!-- FEATURED_ARTICLE_END -->",
        html, flags=re.DOTALL
    )

    # Replace article list section
    html = re.sub(
        r"<!-- ARTICLE_LIST_START -->.*?<!-- ARTICLE_LIST_END -->",
        f"<!-- ARTICLE_LIST_START -->\n{new_list}\n<!-- ARTICLE_LIST_END -->",
        html, flags=re.DOTALL
    )

    return html


def main():
    print(f"Fetching RSS from {RSS_URL}...")
    try:
        xml_bytes = fetch_rss()
    except Exception as e:
        print(f"Error fetching RSS: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsing articles...")
    articles = parse_articles(xml_bytes)
    print(f"Found {len(articles)} articles")
    for i, a in enumerate(articles):
        print(f"  {'[FEATURED]' if i==0 else f'[{i}]      '} {a['title'][:60]}")

    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    updated = update_html(html, articles)

    if updated == html:
        print("No changes detected.")
    else:
        with open(HTML_FILE, "w", encoding="utf-8") as f:
            f.write(updated)
        print(f"Updated {HTML_FILE} successfully.")


if __name__ == "__main__":
    main()
