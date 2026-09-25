#!/usr/bin/env python3
"""Build a clean full-text RSS feed from MirF's official Atom feed."""
from __future__ import annotations
import argparse, hashlib, json, re, time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import format_datetime
from html import escape
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup, Comment
from lxml import etree
BASE_URL="https://www.mirf.ru"; SOURCE_FEED_URL=f"{BASE_URL}/feed"; PUBLIC_BASE_URL="https://drosan-dev.github.io/mirf-koreader-feed"; TIMEOUT=45
PAGE_STYLE="body{font-family:serif;line-height:1.45;margin:1em}img{max-width:100%;height:auto}figure{margin:1em 0}figcaption{font-size:.85em;font-style:italic;margin-top:.35em}blockquote{margin:1em .4em;padding:.25em .8em;border-left:4px solid #555}aside{margin:1em 0;padding:.7em;border:1px solid #777}h2,h3,h4{margin-top:1.4em;margin-bottom:.5em}ul,ol{padding-left:1.5em}"
@dataclass
class Article:
 url:str; title:str; description:str; published:datetime; author:str; category:str; html:str

def fetch(session,url):
 last=None
 for attempt in range(4):
  try:
   r=session.get(url,timeout=TIMEOUT); r.raise_for_status(); return r.text
  except requests.RequestException as exc:
   last=exc
   if attempt<3: time.sleep(2**attempt)
 raise RuntimeError(f"Could not fetch {url}: {last}")

def discover_entries(session):
 root=etree.fromstring(fetch(session,SOURCE_FEED_URL).encode()); ns={"a":"http://www.w3.org/2005/Atom"}; out=[]
 for e in root.xpath("a:entry",namespaces=ns):
  links=e.xpath('a:link[@rel="alternate"]/@href',namespaces=ns) or e.xpath("a:link/@href",namespaces=ns)
  if not links: continue
  url=urljoin(BASE_URL,links[0]).split("#",1)[0]
  if not urlparse(url).netloc.endswith("mirf.ru"): continue
  out.append({"url":url,"description":" ".join(e.xpath("a:summary//text()",namespaces=ns)).strip(),"published":"".join(e.xpath("a:published/text() | a:updated/text()",namespaces=ns)[:1]),"author":" ".join(e.xpath("a:author/a:name//text()",namespaces=ns)).strip()})
 if not out: raise RuntimeError("MirF official feed contains no usable entries")
 return out

def schema_data(soup):
 for node in soup.select('script[type="application/ld+json"]'):
  try: value=json.loads(node.get_text())
  except (json.JSONDecodeError,TypeError): continue
  for item in value.get("@graph",[]) if isinstance(value,dict) else []:
   if isinstance(item,dict) and item.get("datePublished"): return item
 return {}

def clean_content(soup,url,cover=""):
 content=soup.select_one(".news-content .grid-cols-left")
 if content is None: raise RuntimeError(f"Main article content not found: {url}")

 # Interactive content does not work in EPUB. Keep a useful link for quizzes,
 # retain a compact podcast description, and remove video players entirely.
 for quiz in list(content.select(".news-quiz")):
  notice=soup.new_tag("aside")
  title=soup.new_tag("p"); strong=soup.new_tag("strong"); strong.string="Интерактивный тест"
  title.append(strong); notice.append(title)
  text=soup.new_tag("p"); text.string="Этот тест работает только на сайте Мир фантастики."
  notice.append(text)
  link=soup.new_tag("a",href=url); link.string="Пройти тест на сайте"
  notice.append(link); quiz.replace_with(notice)
 for podcast in content.select(".section-podcast"):
  for node in podcast.select(".podcast-subscribe, .podcast-descr__footer"): node.decompose()
  link=soup.new_tag("p"); anchor=soup.new_tag("a",href=url); anchor.string="Открыть выпуск на сайте Мир фантастики"
  link.append(anchor); podcast.append(link)

 selectors=["script","style","noscript","iframe","form","button","video",".news-video",".video-list",".video-preview",".advt-mf",".news-advt",".message-repost",".share",".news-su_see_also",".articles",".comments",".social",".news-author",".news-hash",".news-d-line",".advt","[class*='advert']","[class*='banner']","[class*='repost']"]
 for selector in selectors:
  for node in content.select(selector): node.decompose()

 # Preserve MirF-specific meaning with simple semantic HTML that renders well
 # on monochrome readers even when the original site CSS is unavailable.
 for quote in list(content.select(".mf-quote")):
  block=soup.new_tag("blockquote")
  subtitle=quote.select_one(".mf-quote__subtitle")
  title=quote.select_one(".mf-quote__title")
  label=(subtitle or title)
  if label:
   p=soup.new_tag("p"); strong=soup.new_tag("strong")
   strong.string=label.get_text(" ",strip=True); p.append(strong); block.append(p)
  description=quote.select_one(".mf-quote__description")
  if description:
   for child in list(description.contents): block.append(child.extract())
  else:
   p=soup.new_tag("p"); p.string=quote.get_text(" ",strip=True); block.append(p)
  quote.replace_with(block)

 for callout in list(content.select(".news-su_div")):
  if not callout.get_text(" ",strip=True) and not callout.find("img"):
   callout.decompose(); continue
  callout.name="aside"

 for floating in content.select(".news-float"): floating.name="aside"
 for bold in content.find_all("b"): bold.name="strong"

 for caption in content.select(".news-caption"):
  caption.name="figure"
  info=caption.select_one(".block-info")
  if info: info.name="figcaption"

 for gallery in content.select(".news-d-gallery"):
  for node in gallery.select(".slider-arrow-left, .slider-arrow-right, .slider-pagin"): node.decompose()

 for comment in content.find_all(string=lambda x:isinstance(x,Comment)): comment.extract()
 for picture in list(content.find_all("picture")):
  old=picture.find("img"); src=(old.get("src") or old.get("data-src")) if old else None
  if not src: picture.decompose(); continue
  img=soup.new_tag("img",src=urljoin(url,src))
  if old.get("alt"): img["alt"]=old["alt"]
  picture.replace_with(img)
 for node in content.find_all(True):
  if node.name=="img":
   src=node.get("src") or node.get("data-src")
   if not src: node.decompose(); continue
   node["src"]=urljoin(url,src)
  elif node.name=="a" and node.get("href"): node["href"]=urljoin(url,node["href"])
  node.attrs={k:v for k,v in node.attrs.items() if k in {"href","src","alt","title"}}
 allowed={"a","aside","blockquote","br","div","em","figcaption","figure","h2","h3","h4","hr","i","img","li","ol","p","span","strong","sub","sup","table","tbody","td","th","thead","tr","u","ul"}
 for node in list(content.find_all(True)):
  if node.name not in allowed: node.unwrap()
 if cover:
  cover=urljoin(url,cover); first=content.find("img",src=True)
  if first is None or first.get("src")!=cover:
   fig=soup.new_tag("figure"); fig.append(soup.new_tag("img",src=cover,alt="")); content.insert(0,fig)
 return "".join(str(x) for x in content.contents).strip()

def parse_article(session,entry):
 url=entry["url"]; soup=BeautifulSoup(fetch(session,url),"lxml"); data=schema_data(soup); title=soup.select_one("h1")
 if title is None: raise RuntimeError(f"Title not found: {url}")
 raw=data.get("datePublished") or entry.get("published")
 published=datetime.fromisoformat(raw.replace("Z","+00:00")); a=data.get("author","")
 if isinstance(a,list): author=", ".join(x.get("name","") for x in a if isinstance(x,dict))
 elif isinstance(a,dict): author=a.get("name","")
 else: author=str(a or "")
 category=soup.select_one(".news-header .tag-colors-name"); cover=soup.select_one('meta[property="og:image"][content]')
 description=data.get("description")
 if not isinstance(description,str): description=entry.get("description","")
 if not isinstance(description,str): description=""
 return Article(url,title.get_text(" ",strip=True),re.sub(r"\s+"," ",description).strip(),published,(author or entry.get("author","")).strip(),category.get_text(" ",strip=True) if category else "",clean_content(soup,url,cover.get("content","") if cover else ""))

def page_name(url): return hashlib.sha256(url.encode()).hexdigest()[:20]+".html"
def write_pages(articles,out):
 pages=out/"items"; pages.mkdir(parents=True,exist_ok=True); expected=set()
 for a in articles:
  name=page_name(a.url); expected.add(name); doc=f'<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"><title>{escape(a.title)}</title><style>{PAGE_STYLE}</style></head><body><h1>{escape(a.title)}</h1><article>{a.html}</article></body></html>'; (pages/name).write_text(doc,encoding="utf-8")
 for old in pages.glob("*.html"):
  if old.name not in expected: old.unlink()

def build_feed(articles):
 rss=etree.Element("rss",version="2.0",nsmap={"content":"http://purl.org/rss/1.0/modules/content/"}); ch=etree.SubElement(rss,"channel")
 fields={"title":"Мир фантастики — полный текст для KOReader","link":SOURCE_FEED_URL,"description":"30 последних публикаций mirf.ru с очищенным полным текстом и оригинальными изображениями","language":"ru-ru","lastBuildDate":format_datetime(datetime.now(timezone.utc)),"generator":"mirf-koreader-feed","ttl":"180"}
 for k,v in fields.items(): etree.SubElement(ch,k).text=v
 for a in sorted(articles,key=lambda x:x.published,reverse=True)[:30]:
  item=etree.SubElement(ch,"item"); etree.SubElement(item,"title").text=a.title; etree.SubElement(item,"link").text=f"{PUBLIC_BASE_URL}/items/{page_name(a.url)}"; etree.SubElement(item,"guid",isPermaLink="true").text=a.url; etree.SubElement(item,"pubDate").text=format_datetime(a.published)
  if a.author: etree.SubElement(item,"author").text=a.author
  if a.category: etree.SubElement(item,"category").text=a.category
  etree.SubElement(item,"description").text=a.description; full=etree.SubElement(item,"{http://purl.org/rss/1.0/modules/content/}encoded"); full.text=etree.CDATA(a.html)
 return etree.tostring(rss,xml_declaration=True,encoding="UTF-8",pretty_print=True)

def main():
 p=argparse.ArgumentParser(); p.add_argument("--output",default="public/feed.xml"); p.add_argument("--limit",type=int,default=30); args=p.parse_args(); session=requests.Session(); session.headers.update({"User-Agent":"mirf-koreader-feed/1.0","Accept-Language":"ru"}); articles=[]
 for i,e in enumerate(discover_entries(session),1): print(f"[{i}] {e['url']}",flush=True); articles.append(parse_article(session,e))
 old=Path(args.output)
 if old.exists():
  seen={a.url for a in articles}
  for item in etree.parse(str(old)).xpath("/rss/channel/item"):
   url=item.findtext("guid","")
   if not url or url in seen: continue
   articles.append(Article(url,item.findtext("title",""),item.findtext("description",""),datetime.strptime(item.findtext("pubDate"),"%a, %d %b %Y %H:%M:%S %z"),item.findtext("author",""),item.findtext("category",""),item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded",""))); seen.add(url)
 articles=sorted(articles,key=lambda x:x.published,reverse=True)[:args.limit]; xml=build_feed(articles); out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True); write_pages(articles,out.parent); out.write_bytes(xml); print(f"Wrote {out} ({len(articles)} items)")
if __name__=="__main__": main()


def validate_feed(xml,expected):
 root=etree.fromstring(xml); items=root.xpath("/rss/channel/item")
 if len(items)!=expected: raise RuntimeError(f"Feed has {len(items)} items; expected {expected}")
 for item in items:
  body=item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded","")
  if len(BeautifulSoup(body,"lxml").get_text(" ",strip=True))<100: raise RuntimeError("Article body is unexpectedly short")
