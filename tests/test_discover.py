import unittest
from datetime import datetime, timezone
from generate_feed import Article, build_catalog, build_feed, page_name, validate_feed


class ReedDiscoverTest(unittest.TestCase):
    def article(self):
        return Article(
            "https://example.test/story", "История", "Короткая аннотация",
            datetime(2026, 1, 2, tzinfo=timezone.utc), "Автор", "Книги",
            "<p>" + "слово " * 220 + "</p>", "https://example.test/cover.jpg"
        )

    def test_legacy_feed_contract_is_preserved(self):
        xml = build_feed([self.article()])
        validate_feed(xml, 1)
        self.assertIn(b"<rss", xml)
        self.assertIn(b"content:encoded", xml)
        self.assertIn(b"https://example.test/story", xml)

    def test_catalog_contains_ui_fields_and_reader_link(self):
        data = build_catalog([self.article()])
        item = data["articles"][0]
        self.assertEqual(item["sourceId"], "mirf")
        self.assertEqual(item["readingMinutes"], 1)
        self.assertEqual(item["readerUrl"], f"items/{page_name(item['url'])}")


if __name__ == "__main__":
    unittest.main()
