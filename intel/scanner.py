"""
Scanner — market signal reader.
Sources: HN Show HN, HN Ask HN (filters for "who wants" requests), GitHub Trending, evergreen.
REFINED: noise filter removes non-actionable HN posts, deduplicates by title hash.
"""
from __future__ import annotations
import hashlib
import requests
from dataclasses import dataclass
from loguru import logger


@dataclass
class RawOpportunity:
    title: str
    url: str
    source: str
    score: int = 0

    def uid(self) -> str:
        return hashlib.md5(self.title.encode()).hexdigest()[:8]


# Words that indicate a post is NOT a buildable opportunity
_NOISE_PATTERNS = [
    "ask hn: who is hiring",
    "ask hn: who wants to be hired",
    "freelancer",
    "tell hn:",
    "show hn: i",  # personal projects being shown, not wanted
    "meta: ",
    "is there a way to",
    "what happened to",
    "why did",
    "anyone else",
    "unpopular opinion",
]

# Words that signal actual demand/request
_DEMAND_SIGNALS = [
    "who wants",
    "looking for",
    "need a tool",
    "wish there was",
    "why isn't there",
    "does anyone know of",
    "is there a tool",
    "looking for a",
    "show hn",  # people showing tools = market validation
    "launch",
]


def _is_noise(title: str) -> bool:
    t = title.lower()
    return any(p in t for p in _NOISE_PATTERNS)


def _has_demand(title: str) -> bool:
    t = title.lower()
    return any(p in t for p in _DEMAND_SIGNALS)


def _dedup(opps: list[RawOpportunity]) -> list[RawOpportunity]:
    seen = set()
    result = []
    for o in opps:
        uid = o.uid()
        if uid not in seen:
            seen.add(uid)
            result.append(o)
    return result


def _hn_stories(story_type: str, limit: int = 30) -> list[RawOpportunity]:
    try:
        url = f"https://hacker-news.firebaseio.com/v0/{story_type}stories.json"
        ids = requests.get(url, timeout=10).json()[:limit]
        items = []
        for sid in ids:
            try:
                item = requests.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{sid}.json", timeout=5
                ).json()
                if not item or "title" not in item:
                    continue
                title = item["title"]
                if _is_noise(title):
                    continue
                # For Ask HN: only keep demand signals
                if story_type == "ask" and not _has_demand(title):
                    continue
                items.append(RawOpportunity(
                    title=title,
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
        resp = requests.get(
            "https://github.com/trending/python?since=weekly",
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for repo in soup.select("article.Box-row")[:20]:
            h2 = repo.select_one("h2 a")
            if not h2:
                continue
            name = h2.get_text(strip=True).replace("\n", "").replace(" ", "")
            desc_el = repo.select_one("p")
            desc = desc_el.get_text(strip=True) if desc_el else ""
            stars_el = repo.select_one("span.Counter")
            stars = 0
            if stars_el:
                try:
                    stars = int(stars_el.get_text(strip=True).replace(",", ""))
                except ValueError:
                    pass
            # Only include repos with a description (signal they have a clear purpose)
            if not desc:
                continue
            results.append(RawOpportunity(
                title=f"{name}: {desc}",
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
    RawOpportunity("One-time payment SaaS for small business invoicing — no subscriptions", "local", "evergreen"),
    RawOpportunity("Browser extension for deep work focus tracking", "local", "evergreen"),
    RawOpportunity("Static site generator with zero configuration needed", "local", "evergreen"),
    RawOpportunity("API wrapper for popular service with significantly better developer experience", "local", "evergreen"),
    RawOpportunity("Markdown-first documentation tool that deploys in one command", "local", "evergreen"),
    RawOpportunity("Desktop app for note taking with one-time payment pricing", "local", "evergreen"),
    RawOpportunity("Python package for common ML preprocessing and feature engineering", "local", "evergreen"),
    RawOpportunity("Lightweight alternative to heavyweight SaaS tools for project management", "local", "evergreen"),
    RawOpportunity("Terminal-based dashboard for monitoring personal finance and budgets", "local", "evergreen"),
]


class Scanner:
    def scan(self, include_evergreen: bool = True) -> list[RawOpportunity]:
        logger.info("Scanning market...")
        results: list[RawOpportunity] = []

        results.extend(_hn_stories("show", limit=25))
        results.extend(_hn_stories("ask", limit=25))
        results.extend(_github_trending())

        if include_evergreen:
            results.extend(EVERGREEN)

        results = _dedup(results)
        # Sort by source score descending
        results.sort(key=lambda o: -o.score)

        logger.info(f"Scan complete: {len(results)} unique opportunities")
        return results


SCANNER = Scanner()
