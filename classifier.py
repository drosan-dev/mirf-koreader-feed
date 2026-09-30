"""Deterministic editorial-value classifier for Russian reading material."""
from __future__ import annotations
import re
from dataclasses import dataclass
from bs4 import BeautifulSoup

@dataclass(frozen=True)
class Classification:
 content_class: str
 confidence: float
 reason: str

ARTICLE_PATTERNS = [
 r"\bразбер[её]м|\bобъясн", r"\bпочему\b|\bкак устроен", r"\bсравн",
 r"\bплюс[ыа]?\b|\bминус[ыа]?\b|\bдостоинств|\bнедостат",
 r"\bна мой взгляд|\bпо моему мнению|\bмы считаем", r"\bвывод[ыа]?\b|\bитог[еи]?\b",
 r"\bанализ|\bисследован", r"\bобзор\b|\bрецензи", r"\bпрактик|\bпример[еы]?\b",
 r"\bоднако\b|\bс другой стороны\b|\bтаким образом\b"
]
NEWS_PATTERNS = [
 r"\bобъявил[аи]?\b|\bсообщил[аи]?\b", r"\bанонсировал|\bпредставил[аи]?\b",
 r"\bвышел|\bсостоялся релиз|\bвыпустил[аи]?\b", r"\bобновлени[ея]\b|\bпатч\b",
 r"\bпродаж[аи].*превыс|\bрекорд\b|\bонлайн\b", r"\bназначен|\bвозглавил",
 r"\bстало известно\b|\bпо данным\b", r"\bсмотрите|\bтрейлер\b",
 r"\bв этом выпуске\b|\bновый выпуск\b|\bподкаст\b"
]
PAYWALL_PATTERNS = [r"подписк.*чтобы читать", r"доступ.*подписк", r"войдите.*продолж", r"материал доступен подписчикам"]

def text_from_html(html: str) -> tuple[str, int, int]:
 soup=BeautifulSoup(html or "", "lxml")
 for node in soup.select("script,style,noscript,nav,header,footer,aside,form"):
  node.decompose()
 root=soup.select_one("article, main, [itemprop='articleBody']") or soup.body or soup
 paragraphs=[re.sub(r"\s+"," ",p.get_text(" ",strip=True)).strip() for p in root.select("p")]
 paragraphs=[p for p in paragraphs if p]
 text="\n".join(paragraphs) or re.sub(r"\s+"," ",root.get_text(" ",strip=True))
 return text, len(paragraphs), len(root.select("h2,h3,h4"))

def classify_text(text: str, paragraph_count: int = 0, heading_count: int = 0, extraction_error: str = "") -> Classification:
 normalized=re.sub(r"\s+"," ",(text or "").lower()).strip(); words=len(normalized.split())
 if extraction_error:
  return Classification("uncertain",0.05,f"Не удалось извлечь страницу: {extraction_error[:140]}")
 if any(re.search(pattern,normalized) for pattern in PAYWALL_PATTERNS) and words < 350:
  return Classification("uncertain",0.18,"Похоже на paywall: самостоятельный текст недоступен")
 article_hits=sum(bool(re.search(pattern,normalized)) for pattern in ARTICLE_PATTERNS)
 news_hits=sum(bool(re.search(pattern,normalized)) for pattern in NEWS_PATTERNS)
 podcast=bool(re.search(r"\b(в этом|новый|свежий) выпуск\b|\bслушайте\b",normalized))
 if words < 80:
  if news_hits >= 3 or (podcast and news_hits >= 2): return Classification("news",.7,f"Короткая служебная или событийная публикация; новостных признаков {news_hits}")
  if article_hits >= 4: return Classification("article",.68,f"Короткий, но самостоятельный разбор; аналитических признаков {article_hits}")
  return Classification("uncertain",0.15,f"Недостаточно основного текста ({words} слов)")
 if (podcast and article_hits <= 1) or (news_hits >= 1 and article_hits == 0 and words < 500):
  confidence=min(.92,.64+news_hits*.07)
  return Classification("news",round(confidence,2),f"Страница сообщает о событии или представляет выпуск без самостоятельного разбора; новостных признаков {news_hits}")
 structure_bonus=(min(heading_count,3)*0.25 + min(paragraph_count/12,1.0)) if article_hits else 0
 article_score=article_hits*1.15 + structure_bonus
 news_score=news_hits*1.1
 if podcast and words < 700: news_score += 2.5
 if article_hits and words >= 700: article_score += 1.2
 elif article_hits and words >= 350: article_score += .55
 if news_score-article_score >= 1.6:
  confidence=min(.96,.58+(news_score-article_score)*.08)
  return Classification("news",round(confidence,2),f"Преобладает сообщение о событии или выпуске; новостных признаков {news_hits}, аналитических {article_hits}")
 if article_score-news_score >= 1.25:
  confidence=min(.96,.58+(article_score-news_score)*.07)
  return Classification("article",round(confidence,2),f"Текст развивает тему или авторскую оценку; аналитических признаков {article_hits}, новостных {news_hits}")
 return Classification("uncertain",round(max(.25,.52-abs(article_score-news_score)*.08),2),f"Сигналы неоднозначны: аналитических {article_hits}, новостных {news_hits}, {words} слов")

def classify_html(html: str, extraction_error: str = "") -> Classification:
 text,paragraphs,headings=text_from_html(html)
 return classify_text(text,paragraphs,headings,extraction_error)
