#!/usr/bin/env python3
"""Build a full-text RSS feed from the latest MirF articles."""

from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Comment, Tag
from lxml import etree

BASE_URL = "https://www.mirf.ru"
ARTICLES_URL = f"{BASE_URL}/articles"
USER_AGENT = "mirf-koreader-feed/1.0 (+https://github.com/)"
TIMEOUT = 45


@dataclass
class Article:
    url: str
    title: str
    description: str
    published: datetime
    author: str
    category: str
    html: str


def fetch(session: requests.Session, url: str) -> str:
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            response = session.get(url, timeout=TIMEOUT)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_error = exc
            if attempt < 3:
                time.sleep(2**attempt)
    raise RuntimeError(f"Could not fetch {url}: {last_error}")


def discover_urls(session: requests.Session, limit: int) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    page = 1
    while len(urls) < limit and page <= 10:
        url = ARTICLES_URL if page == 1 else f"{ARTICLES_URL}?page={page}"
        soup = BeautifulSoup(fetch(session, url), "lxml")
        cards = soup.select(".articles-grid a.card[href]")
        if not cards:
            break
        for card in cards:
            absolute = urljoin(BASE_URL, card["href"]).split("#", 1)[0]
            if urlparse(absolute).netloc.endswith("mirf.ru") and absolute not in seen:
                seen.add(absolute)
                urls.append(absolute)
                if len(urls) == limit:
                    break
        page += 1
    if len(urls) < limit:
        raise RuntimeError(f"Found only {len(urls)} article URLs (wanted {limit})")
    return urls


def schema_data(soup: BeautifulSoup) -> dict:
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            value = json.loads(node.get_text())
        except (json.JSONDecodeError, TypeError):
            continue
        graph = value.get("@graph", []) if isinstance(value, dict) else []
        for item in graph:
            if isinstance(item, dict) and item.get("datePublished"):
                return item
    return {}


def clean_content(soup: BeautifulSoup, page_url: str) -> str:
    content = soup.select_one(".news-content .grid-cols-left")
    if content is None:
        raise RuntimeError(f"Main article content not found: {page_url}")

    # Remove widgets, adverts, sharing controls and executable/embedded content.
    remove_selectors = [
        "script", "style", "noscript", "iframe", "form", "button",
        ".advt-mf", ".news-advt", ".message-repost", ".share",
        ".news-su_see_also", ".articles", ".comments", ".social",
        "[class*='advert']", "[class*='banner']", "[class*='repost']",
    ]
    for selector in remove_selectors:
        for node in content.select(selector):
            node.decompose()
    for comment in content.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()

    # Use the original full-size image and discard responsive wrappers.
    for picture in list(content.find_all("picture")):
        source_img = picture.find("img")
        if source_img is None:
            picture.decompose()
            continue
        src = source_img.get("src") or source_img.get("data-src")
        if not src:
            picture.decompose()
            continue
        img = soup.new_tag("img", src=urljoin(page_url, src))
        if source_img.get("alt"):
            img["alt"] = source_img["alt"]
        picture.replace_with(img)

    for node in content.find_all(True):
        if node.name == "img":
            src = node.get("src") or node.get("data-src")
            if src:
                node["src"] = urljoin(page_url, src)
            else:
                node.decompose()
                continue
        elif node.name == "a" and node.get("href"):
            node["href"] = urljoin(page_url, node["href"])
        allowed = {"href", "src", "alt", "title"}
        node.attrs = {key: value for key, value in node.attrs.items() if key in allowed}

    # Unwrap layout-only containers while retaining headings, paragraphs and media.
    allowed_tags = {
        "a", "blockquote", "br", "div", "em", "figcaption", "figure",
        "h2", "h3", "h4", "hr", "i", "img", "li", "ol", "p", "span",
        "strong", "sub", "sup", "table", "tbody", "td", "th", "thead",
        "tr", "u", "ul",
    }
    for node in list(content.find_all(True)):
        if node.name not in allowed_tags:
            node.unwrap()
    return "".join(str(child) for child in content.contents).strip()


def parse_article(session: requests.Session, url: str) -> Article:
    soup = BeautifulSoup(fetch(session, url), "lxml")
    data = schema_data(soup)
    title_node = soup.select_one("h1")
    if title_node is None:
        raise RuntimeError(f"Title not found: {url}")
    published_raw = data.get("datePublished")
    if not published_raw:
        raise RuntimeError(f"Publication date not found: {url}")
    published = datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
    author_data = data.get("author", "")
    if isinstance(author_data, list):
        author = ", ".join(x.get("name", "") for x in author_data if isinstance(x, dict))
    elif isinstance(author_data, dict):
        author = author_data.get("name", "")
    else:
        author = str(author_data or "")
    category_node = soup.select_one(".news-header .tag-colors-name")
    description = data.get("description", "")
    return Article(
        url=url,
        title=title_node.get_text(" ", strip=True),
        description=re.sub(r"\s+", " ", description).strip(),
        published=published,
        author=author.strip(),
        category=category_node.get_text(" ", strip=True) if category_node else "",
        html=clean_content(soup, url),
    )


def build_feed(articles: list[Article]) -> bytes:
    nsmap = {"content": "http://purl.org/rss/1.0/modules/content/"}
    rss = etree.Element("rss", version="2.0", nsmap=nsmap)
    channel = etree.SubElement(rss, "channel")
    fields = {
        "title": "Мир фантастики — полный текст для KOReader",
        "link": ARTICLES_URL,
        "description": "30 последних материалов mirf.ru с полным текстом и оригинальными изображениями",
        "language": "ru-ru",
        "lastBuildDate": format_datetime(datetime.now(timezone.utc)),
        "generator": "mirf-koreader-feed",
        "ttl": "180",
    }
    for name, value in fields.items():
        etree.SubElement(channel, name).text = value
    for article in sorted(articles, key=lambda x: x.published, reverse=True)[:30]:
        item = etree.SubElement(channel, "item")
        etree.SubElement(item, "title").text = article.title
        etree.SubElement(item, "link").text = article.url
        etree.SubElement(item, "guid", isPermaLink="true").text = article.url
        etree.SubElement(item, "pubDate").text = format_datetime(article.published)
        if article.author:
            etree.SubElement(item, "author").text = article.author
        if article.category:
            etree.SubElement(item, "category").text = article.category
        etree.SubElement(item, "description").text = article.description
        full = etree.SubElement(item, "{http://purl.org/rss/1.0/modules/content/}encoded")
        full.text = etree.CDATA(article.html)
    return etree.tostring(rss, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def validate_feed(xml: bytes, expected: int) -> None:
    root = etree.fromstring(xml)
    items = root.xpath("/rss/channel/item")
    if len(items) != expected:
        raise RuntimeError(f"Feed has {len(items)} items; expected {expected}")
    for item in items:
        link = item.findtext("link", "")
        encoded = item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded", "")
        if not link.startswith("https://www.mirf.ru/"):
            raise RuntimeError(f"Invalid item URL: {link}")
        if len(BeautifulSoup(encoded, "lxml").get_text(" ", strip=True)) < 100:
            raise RuntimeError(f"Article body is unexpectedly short: {link}")
        if re.search(r"<(script|iframe|form)\b", encoded, re.I):
            raise RuntimeError(f"Unsafe tag remains in article: {link}")
        for img in BeautifulSoup(encoded, "lxml").find_all("img", src=True):
            if not img["src"].startswith(("https://www.mirf.ru/", "https://mirf.ru/")):
                raise RuntimeError(f"Non-MirF image URL: {img['src']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="public/feed.xml")
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    if not 1 <= args.limit <= 30:
        parser.error("--limit must be between 1 and 30")
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "ru,en;q=0.8"})
    urls = discover_urls(session, args.limit)
    articles = []
    for index, url in enumerate(urls, 1):
        print(f"[{index}/{len(urls)}] {url}", flush=True)
        articles.append(parse_article(session, url))
    xml = build_feed(articles)
    validate_feed(xml, args.limit)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(xml)
    print(f"Wrote {output} ({len(xml):,} bytes, {len(articles)} items)")


if __name__ == "__main__":
    main()
