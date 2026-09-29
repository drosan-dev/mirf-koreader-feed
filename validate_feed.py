#!/usr/bin/env python3
import json
from pathlib import Path
from generate_feed import validate_feed

xml = Path("public/feed.xml").read_bytes()
validate_feed(xml, 30)
catalog = json.loads(Path("public/data/articles.json").read_text(encoding="utf-8"))
if not Path("public/data/articles.js").exists():
    raise RuntimeError("data/articles.js is missing")
if catalog.get("version") != 1 or len(catalog.get("articles", [])) < 30:
    raise RuntimeError("data/articles.json must contain at least 30 version-1 articles")
required = {"id", "title", "source", "summary", "readingMinutes", "url", "readerUrl"}
for article in catalog["articles"]:
    if required - article.keys() or (article["readingMinutes"] is not None and article["readingMinutes"] < 1):
        raise RuntimeError(f"Invalid catalog article: {article.get('title', article)}")
print(f"feed.xml and Reed Discover catalog are valid ({len(xml):,} bytes, 30 items)")

