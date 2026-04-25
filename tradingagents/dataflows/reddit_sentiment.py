# -*- coding: utf-8 -*-
"""Reddit-based retail sentiment fetching via public JSON API."""

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
import yfinance as yf

logger = logging.getLogger(__name__)

_SUBREDDITS = ["wallstreetbets", "stocks", "options"]
_COMMENT_PREVIEW = 200
_TOP_POSTS_WITH_COMMENTS = 3
_TIMEOUT = 10
_REQUEST_DELAY = 0.5   # seconds between requests — stays within Reddit's rate limit

# Compliant user-agent format Reddit requires:
#   <platform>:<app-id>:<version> (by /u/<username>)
# Override via REDDIT_USER_AGENT env var if needed.
_USER_AGENT = os.getenv(
    "REDDIT_USER_AGENT",
    "python:com.tradingagents:v1.0 (by /u/tradingagents_bot)",
)
_HEADERS = {"User-Agent": _USER_AGENT}

_CACHE_DIR = os.getenv(
    "TRADINGAGENTS_CACHE_DIR",
    os.path.join(os.path.expanduser("~"), ".tradingagents", "cache"),
)
_BOT_AUTHORS = {"automoderator", "visualmod"}


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_path(ticker: str) -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    return Path(_CACHE_DIR) / "reddit" / f"{ticker.upper()}-reddit-{today}.json"


def _read_cache(path: Path):
    """Return cached result string if today's file exists, else None."""
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("date") == datetime.now().strftime("%Y-%m-%d"):
            return data.get("result")
    except Exception:
        pass
    return None


def _write_cache(path: Path, result: str) -> None:
    """Write result to cache; log warning on failure, never raise."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"date": datetime.now().strftime("%Y-%m-%d"), "result": result}
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logger.warning("Reddit cache write failed (non-fatal): %s", exc)


# ---------------------------------------------------------------------------
# Company name lookup
# ---------------------------------------------------------------------------

def _get_company_name(ticker: str) -> str:
    try:
        info = yf.Ticker(ticker).info
        return info.get("shortName") or info.get("longName") or ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------

def _search_subreddit(subreddit: str, query: str) -> list:
    """Fetch up to 25 posts from a subreddit matching query."""
    params = {"q": query, "restrict_sr": 1, "sort": "relevance", "limit": 25, "t": "week"}
    time.sleep(_REQUEST_DELAY)
    try:
        r = requests.get(
            f"https://www.reddit.com/r/{subreddit}/search.json",
            params=params, headers=_HEADERS, timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("Reddit search failed for r/%s: %s", subreddit, exc)
        return []
    if r.status_code == 429:
        logger.warning("Reddit rate limit hit (429) for r/%s", subreddit)
        return []
    if not r.ok:
        logger.warning("Reddit returned HTTP %s for r/%s", r.status_code, subreddit)
        return []
    r.encoding = "utf-8"
    try:
        return r.json().get("data", {}).get("children", [])
    except ValueError:
        return []


def _fetch_top_comments(subreddit: str, post_id: str, limit: int = 20) -> list:
    """Fetch top-level comments for a post sorted by score."""
    time.sleep(_REQUEST_DELAY)
    try:
        r = requests.get(
            f"https://www.reddit.com/r/{subreddit}/comments/{post_id}.json",
            params={"sort": "top", "limit": limit, "depth": 1},
            headers=_HEADERS, timeout=_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("Reddit comment fetch failed for %s/%s: %s", subreddit, post_id, exc)
        return []
    if r.status_code == 429:
        logger.warning("Reddit rate limit hit (429) fetching comments for %s", post_id)
        return []
    if not r.ok:
        return []
    r.encoding = "utf-8"
    try:
        data = r.json()
    except ValueError:
        return []
    if len(data) < 2:
        return []
    comments = []
    for item in data[1].get("data", {}).get("children", []):
        cdata = item.get("data", {})
        if cdata.get("author", "").lower() in _BOT_AUTHORS:
            continue
        body = cdata.get("body", "")
        if not body or body in ("[deleted]", "[removed]"):
            continue
        comments.append(" ".join(body.split())[:_COMMENT_PREVIEW])
    return comments


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_reddit_sentiment(ticker: str, days: int = 3) -> str:
    """
    Fetch recent Reddit posts mentioning a ticker from investing subreddits
    (r/wallstreetbets, r/stocks, r/options) via Reddit's public JSON API.

    Results are cached to disk keyed by (ticker, today's date). Repeat calls
    within the same calendar day return instantly from cache.

    Returns an empty string on API failure.
    """
    ticker = ticker.upper()

    cache_path = _cache_path(ticker)
    cached = _read_cache(cache_path)
    if cached is not None:
        logger.debug("Reddit cache hit for %s", ticker)
        return cached

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days)
    company_name = _get_company_name(ticker)
    name_keyword = ""
    if company_name:
        first_word = company_name.split()[0]
        if len(first_word) > 3 and first_word.upper() != ticker:
            name_keyword = first_word

    search_terms = [ticker] + ([name_keyword] if name_keyword else [])
    seen_ids: set = set()
    all_posts: list = []

    for subreddit in _SUBREDDITS:
        for term in search_terms:
            for item in _search_subreddit(subreddit, term):
                post = item.get("data", {})
                post_id = post.get("id", "")
                if post_id in seen_ids:
                    continue
                title_lower = post.get("title", "").lower()
                if ticker.lower() not in title_lower and (
                    not name_keyword or name_keyword.lower() not in title_lower
                ):
                    continue
                created_utc = post.get("created_utc", 0)
                if datetime.fromtimestamp(created_utc, tz=timezone.utc) < cutoff:
                    continue
                seen_ids.add(post_id)
                all_posts.append({
                    "id": post_id,
                    "subreddit": subreddit,
                    "title": post.get("title", ""),
                    "score": post.get("score", 0),
                    "num_comments": post.get("num_comments", 0),
                    "upvote_ratio": post.get("upvote_ratio", 0.0),
                    "flair": post.get("link_flair_text") or "",
                })

    if not all_posts:
        result = (
            f"No Reddit posts found mentioning {ticker} in the last {days} days "
            f"across r/wallstreetbets, r/stocks, r/options."
        )
        _write_cache(cache_path, result)
        return result

    all_posts.sort(key=lambda p: p["score"], reverse=True)

    for post in all_posts[:_TOP_POSTS_WITH_COMMENTS]:
        post["comments"] = _fetch_top_comments(post["subreddit"], post["id"])

    label = f"{ticker}" + (f" / {name_keyword}" if name_keyword else "")
    lines = [f"Reddit posts mentioning {label} (last {days} days, sorted by upvotes):\n"]
    for p in all_posts:
        flair = f" [{p['flair']}]" if p["flair"] else ""
        lines.append(
            f"r/{p['subreddit']}{flair} | Score: {p['score']} | "
            f"Comments: {p['num_comments']} | "
            f"Upvote ratio: {p['upvote_ratio']:.0%} | {p['title']}"
        )
        for c in p.get("comments", []):
            lines.append(f"  > {c}")

    result = "\n".join(lines)
    _write_cache(cache_path, result)
    return result
