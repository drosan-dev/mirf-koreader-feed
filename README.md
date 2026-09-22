# MirF full-text RSS for KOReader

Generates an RSS 2.0 feed containing the 30 latest items from
[`mirf.ru/articles`](https://www.mirf.ru/articles). Each item contains the
cleaned full article in `content:encoded`; images keep their original MirF URLs.

The GitHub Actions workflow rebuilds and publishes the feed to GitHub Pages
every three hours. It can also be started manually from the Actions tab.

## Feed URL

```text
https://drosan-dev.github.io/mirf-koreader-feed/feed.xml
```

## KOReader

1. Open the top menu and choose **News downloader (RSS/Atom)**.
2. Choose **Edit news feeds**, then **Add new feed**.
3. Paste the feed URL above and set the limit to `30`.
4. Keep **Download full article** off: the feed already contains the cleaned
   full text. Turn **Include images** on if images should be saved in the EPUB.
5. Go back to **News downloader (RSS/Atom)** and choose **Sync news feeds**.
6. After the download finishes, choose **Go to news folder**.

## Local run

```bash
python -m pip install -r requirements.txt
python generate_feed.py
python validate_feed.py
```

The generated file is `public/feed.xml`.

MirF owns the article text and images. This project only transforms publicly
available pages into a personal reader-friendly feed and does not mirror image
files.
