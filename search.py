import os
import time
import random
import requests
from typing import Optional
from urllib.parse import urlparse as _urlparse

_AGGREGATOR_DOMAINS = [
    "yelp.com", "yellowpages.com", "tripadvisor.com", "google.com",
    "facebook.com", "instagram.com", "twitter.com", "linkedin.com",
    "wikipedia.org", "reddit.com", "amazon.com", "trustpilot.com",
    "glassdoor.com", "indeed.com", "zomato.com", "justdial.com",
    "foursquare.com", "bing.com", "yahoo.com", "maps.google.com",
]

def is_aggregator(url: str) -> bool:
    try:
        domain = _urlparse(url).netloc.lower().replace("www.", "")
        return any(agg in domain for agg in _AGGREGATOR_DOMAINS)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# User-agent pool
# ---------------------------------------------------------------------------
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 OPR/108.0.0.0",
]

SERPER_API_KEY = "ed92cd653e12f00849abbdedd5dd835efa952391"
SERPER_URL = "https://google.serper.dev/search"


def _random_delay():
    """Sleep for a random 2–5 second delay."""
    time.sleep(random.uniform(2, 5))


def _get_proxies() -> Optional[dict]:
    """Return proxy config from env var PROXY_URL, or None."""
    proxy_url = os.environ.get("PROXY_URL")
    if proxy_url:
        return {"http": proxy_url, "https": proxy_url}
    return None


def _rotate_headers() -> dict:
    """Return headers with a randomly chosen user-agent."""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }


# ---------------------------------------------------------------------------
# Primary: Serper
# ---------------------------------------------------------------------------
def search_serper(industry: str, area: str, max_results: int = 20) -> list[dict]:
    """Query Serper (Google) and return list of business dicts."""
    query = f"{industry} in {area}"
    payload = {"q": query, "num": min(max_results, 100)}
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json",
    }
    proxies = _get_proxies()

    response = requests.post(
        SERPER_URL,
        json=payload,
        headers=headers,
        proxies=proxies,
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()

    results = []

    # Organic results
    for item in data.get("organic", [])[:max_results]:
        results.append(
            {
                "business_name": item.get("title", "").strip(),
                "source_url": item.get("link", "").strip(),
                "snippet": item.get("snippet", "").strip(),
                "source": "Google (Serper)",
            }
        )

    # Knowledge graph if present
    kg = data.get("knowledgeGraph", {})
    if kg and len(results) < max_results:
        results.insert(
            0,
            {
                "business_name": kg.get("title", "").strip(),
                "source_url": kg.get("website", "").strip(),
                "snippet": kg.get("description", "").strip(),
                "source": "Google Knowledge Graph",
            },
        )

    return results[:max_results]


# ---------------------------------------------------------------------------
# Fallback 1: Bing
# ---------------------------------------------------------------------------
def search_bing(industry: str, area: str, max_results: int = 20) -> list[dict]:
    """Scrape Bing search results as a fallback."""
    query = f"{industry} in {area}"
    url = "https://www.bing.com/search"
    params = {"q": query, "count": max_results}
    proxies = _get_proxies()

    _random_delay()
    response = requests.get(
        url,
        params=params,
        headers=_rotate_headers(),
        proxies=proxies,
        timeout=15,
    )
    response.raise_for_status()

    from html.parser import HTMLParser

    class BingParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.results = []
            self._in_title = False
            self._in_snippet = False
            self._current = {}
            self._depth = 0

        def handle_starttag(self, tag, attrs):
            attrs_dict = dict(attrs)
            cls = attrs_dict.get("class", "")
            if tag == "li" and "b_algo" in cls:
                self._current = {}
            if tag == "a" and self._current is not None and "href" in attrs_dict:
                href = attrs_dict["href"]
                if href.startswith("http") and "business_name" not in self._current:
                    self._current["source_url"] = href
                    self._in_title = True
            if tag in ("p", "div") and "b_caption" in cls:
                self._in_snippet = True

        def handle_endtag(self, tag):
            if tag == "a":
                self._in_title = False
            if tag in ("p", "div"):
                self._in_snippet = False
            if tag == "li" and self._current.get("source_url"):
                self.results.append(self._current)
                self._current = {}

        def handle_data(self, data):
            data = data.strip()
            if not data:
                return
            if self._in_title and "business_name" not in self._current:
                self._current["business_name"] = data
            if self._in_snippet and "snippet" not in self._current:
                self._current["snippet"] = data

    parser = BingParser()
    parser.feed(response.text)

    results = []
    for item in parser.results[:max_results]:
        results.append(
            {
                "business_name": item.get("business_name", "Unknown"),
                "source_url": item.get("source_url", ""),
                "snippet": item.get("snippet", ""),
                "source": "Bing",
            }
        )
    return results


# ---------------------------------------------------------------------------
# Fallback 2: DuckDuckGo
# ---------------------------------------------------------------------------
def search_duckduckgo(industry: str, area: str, max_results: int = 20) -> list[dict]:
    """Use DuckDuckGo instant-answer API as second fallback."""
    query = f"{industry} in {area}"
    url = "https://api.duckduckgo.com/"
    params = {
        "q": query,
        "format": "json",
        "no_html": "1",
        "skip_disambig": "1",
    }
    proxies = _get_proxies()

    _random_delay()
    response = requests.get(
        url,
        params=params,
        headers=_rotate_headers(),
        proxies=proxies,
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()

    results = []

    # RelatedTopics
    for topic in data.get("RelatedTopics", [])[:max_results]:
        if isinstance(topic, dict) and "Text" in topic:
            first_url = topic.get("FirstURL", "")
            text = topic.get("Text", "")
            name = text.split(" - ")[0] if " - " in text else text[:60]
            results.append(
                {
                    "business_name": name.strip(),
                    "source_url": first_url,
                    "snippet": text.strip(),
                    "source": "DuckDuckGo",
                }
            )

    # Abstract as top result
    if data.get("AbstractURL") and len(results) < max_results:
        results.insert(
            0,
            {
                "business_name": data.get("Heading", query),
                "source_url": data.get("AbstractURL", ""),
                "snippet": data.get("AbstractText", ""),
                "source": "DuckDuckGo Abstract",
            },
        )

    return results[:max_results]


def _filter_business_only(results: list[dict], max_results: int) -> list[dict]:
    """Remove aggregator / non-business URLs and trim to max_results."""
    filtered = [r for r in results if r.get("source_url") and not is_aggregator(r["source_url"])]
    return filtered[:max_results]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def search(
    industry: str,
    area: str,
    max_results: int = 20,
    progress_callback=None,
) -> tuple[list[dict], str]:
    """
    Search for businesses matching `industry` in `area`.

    Returns (results, engine_used) where results is a list of dicts:
        {business_name, source_url, snippet, source}
    """
    # Fetch a larger buffer so enough results survive after filtering aggregators.
    # E.g. user asks for 2 → fetch up to 20 so filtering still yields 2 business sites.
    BUFFER_MULTIPLIER = 5
    fetch_count = min(max_results * BUFFER_MULTIPLIER, 100)

    if progress_callback:
        progress_callback("🔍 Querying Serper (Google)…")

    try:
        results = search_serper(industry, area, fetch_count)
        results = _filter_business_only(results, max_results)
        if results:
            return results, "Google via Serper"
    except Exception as e:
        if progress_callback:
            progress_callback(f"⚠️ Serper failed ({e}). Trying Bing…")

    _random_delay()

    try:
        results = search_bing(industry, area, fetch_count)
        results = _filter_business_only(results, max_results)
        if results:
            return results, "Bing (fallback)"
    except Exception as e:
        if progress_callback:
            progress_callback(f"⚠️ Bing failed ({e}). Trying DuckDuckGo…")

    _random_delay()

    try:
        results = search_duckduckgo(industry, area, fetch_count)
        results = _filter_business_only(results, max_results)
        if results:
            return results, "DuckDuckGo (fallback)"
    except Exception as e:
        if progress_callback:
            progress_callback(f"❌ All search engines failed: {e}")

    return [], "None"
