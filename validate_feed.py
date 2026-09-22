#!/usr/bin/env python3
from pathlib import Path
from generate_feed import validate_feed

xml = Path("public/feed.xml").read_bytes()
validate_feed(xml, 30)
print(f"feed.xml is valid ({len(xml):,} bytes, 30 items)")

