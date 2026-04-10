"""
Researcher — web research for opportunities and tech questions.
DuckDuckGo HTML scrape + page fetch. No API keys required.
"""
from __future__ import annotations
import requests
from bs4 import BeautifulSoup
from loguru import logger


def _ddg_search(query: str, max_results: int = 5) -> list[dict]:
    try:
        url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(query)}"
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for r in soup.select(".result")[:max_results]:
            title_el = r.select_one(".result__title")
            url_el = r.select_one(".result__url")
            snippet_el = r.select_one(".result__snippet")
            if title_el and url_el:
                results.append({
                    "title": title_el.get_text(strip=True),
                    "url": url_el.get_text(strip=True),
                    "snippet": snippet_el.get_text(strip=True) if snippet_el else "",
                })
        return results
    except Exception as e:
        logger.warning(f"DDG search failed: {e}")
        return []


def _fetch_page(url: str, max_chars: int = 3000) -> str:
    try:
        if not url.startswith("http"):
            url = "https://" + url
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(resp.text, "html.parser")
        # Remove scripts/styles
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()
        text = soup.get_text(separator=" ", strip=True)
        return text[:max_chars]
    except Exception as e:
        logger.warning(f"Page fetch failed for {url}: {e}")
        return ""


class Researcher:
    def research_topic(self, topic: str) -> str:
        """Returns research summary as string for LLM context."""
        results = _ddg_search(topic, max_results=3)
        if not results:
            return f"No results found for: {topic}"

        sections = []
        for r in results:
            content = _fetch_page(r["url"])
            if content:
                sections.append(f"[{r['title']}]\n{content[:800]}")

        return "\n\n".join(sections) if sections else "Research returned no usable content."

    def search(self, query: str) -> str:
        """Raw search results as formatted string."""
        results = _ddg_search(query)
        if not results:
            return "No results."
        lines = [f"- {r['title']}: {r['snippet']} ({r['url']})" for r in results]
        return "\n".join(lines)

    def fetch(self, url: str) -> str:
        return _fetch_page(url)


RESEARCHER = Researcher()
