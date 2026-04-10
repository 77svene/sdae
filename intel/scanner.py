"""
Scanner — reads market signals. Real sources, not synthetic data.
HN Show HN, HN Ask HN ("who wants X"), GitHub Trending, evergreen ideas.
Returns raw opportunity strings for the scorer to evaluate.
"""
from __future__ import annotations
import requests
from dataclasses import dataclass
from loguru import logger


@dataclass
class RawOpportunity:
    title: str
    url: str
    source: str
    score: int = 0  # source score (HN points, stars, etc.)


def _hn_stories(story_type: str, limit: int = 30) -> list[RawOpportunity]:
    """story_type: 'show', 'ask', 'new'"""
    try:
        url = f"https://hacker-news.firebaseio.com/v0/{story_type}stories.json"
        ids = requests.get(url, timeout=10).json()[:limit]
        items = []
        for sid in ids:
            try:
                item = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", timeout=5).json()
                if item and "title" in item:
                    items.append(RawOpportunity(
                        title=item["title"],
                        url=item.get("url", f"https://news.ycombinator.com/item?id={sid}"),
                        source=f"hn_{story_type}",
                        score=item.get("score", 0),
                    ))
            except Exception:
                continue
        return items
    except Exception as e:
        logger.warning(f"HN {story_type} scan failed: {e}")
        return []


def _github_trending() -> list[RawOpportunity]:
    try:
        from bs4 import BeautifulSoup
        resp = requests.get("https://github.com/trending/python?since=weekly", timeout=10,
                            headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for repo in soup.select("article.Box-row")[:20]:
            h2 = repo.select_one("h2 a")
            if h2:
                name = h2.get_text(strip=True).replace("\n", "").replace(" ", "")
                desc_el = repo.select_one("p")
                desc = desc_el.get_text(strip=True) if desc_el else ""
                stars_el = repo.select_one("span.Counter")
                stars = int(stars_el.get_text(strip=True).replace(",", "")) if stars_el else 0
                results.append(RawOpportunity(
                    title=f"{name}: {desc}" if desc else name,
                    url=f"https://github.com/{name.lstrip('/')}",
                    source="github_trending",
                    score=stars,
                ))
        return results
    except Exception as e:
        logger.warning(f"GitHub trending scan failed: {e}")
        return []


EVERGREEN = [
    RawOpportunity("CLI tool for automating repetitive developer tasks", "local", "evergreen"),
    RawOpportunity("Simple SaaS for small business invoicing with no monthly fee", "local", "evergreen"),
    RawOpportunity("Browser extension for productivity tracking", "local", "evergreen"),
    RawOpportunity("Static site generator with zero config", "local", "evergreen"),
    RawOpportunity("API wrapper for popular service with better DX", "local", "evergreen"),
    RawOpportunity("Markdown-based documentation tool", "local", "evergreen"),
    RawOpportunity("One-time payment desktop app for note taking", "local", "evergreen"),
    RawOpportunity("Python package for common ML preprocessing tasks", "local", "evergreen"),
]


class Scanner:
    def scan(self, include_evergreen: bool = True) -> list[RawOpportunity]:
        logger.info("Scanning market...")
        results = []

        results.extend(_hn_stories("show", limit=20))
        results.extend(_hn_stories("ask", limit=20))
        results.extend(_github_trending())

        if include_evergreen:
            results.extend(EVERGREEN)

        logger.info(f"Found {len(results)} raw opportunities")
        return results


SCANNER = Scanner()
