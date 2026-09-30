#!/usr/bin/env python3
import json
from pathlib import Path
from generate_feed import validate_feed

xml = Path("public/feed.xml").read_bytes()
validate_feed(xml, 30)
catalog = json.loads(Path("public/data/articles.json").read_text(encoding="utf-8"))
if not Path("public/data/articles.js").exists():
    raise RuntimeError("data/articles.js is missing")
if catalog.get("version") != 2 or len(catalog.get("articles", [])) < 30:
    raise RuntimeError("data/articles.json must contain at least 30 version-2 articles")
required = {
    "id",
    "title",
    "source",
    "summary",
    "readingMinutes",
    "url",
    "readerUrl",
    "contentClass",
    "classificationConfidence",
    "classificationReason",
    "classificationSource",
}
for article in catalog["articles"]:
    if required - article.keys() or (article["readingMinutes"] is not None and article["readingMinutes"] < 1):
        raise RuntimeError(f"Invalid catalog article: {article.get('title', article)}")
    if article["contentClass"] not in {"article", "news", "uncertain"}:
        raise RuntimeError(f"Invalid content class: {article.get('title', article)}")
    confidence = article["classificationConfidence"]
    if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise RuntimeError(f"Invalid classification confidence: {article.get('title', article)}")
    if not isinstance(article["classificationReason"], str) or not article["classificationReason"].strip():
        raise RuntimeError(f"Missing classification reason: {article.get('title', article)}")
    if article["classificationSource"] not in {"automatic", "manual"}:
        raise RuntimeError(f"Invalid classification source: {article.get('title', article)}")
print(f"feed.xml and Reed Discover catalog are valid ({len(xml):,} bytes, 30 items)")

