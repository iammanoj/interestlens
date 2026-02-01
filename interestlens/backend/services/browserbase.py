"""
Browserbase service for web content extraction and cross-reference search.
Uses Browserbase API for headless browser automation.
"""

import os
import asyncio
import json
from typing import List, Optional
from urllib.parse import urlparse
import weave
import httpx

from models.authenticity import ArticleContent, CrossReferenceResult
from services.weave_utils import trace_news_search, log_metric
from services.redis_client import get_cached_article_content, cache_article_content

BROWSERBASE_API_URL = "https://www.browserbase.com/v1"
BROWSERBASE_API_KEY = os.getenv("BROWSERBASE_API_KEY")
BROWSERBASE_PROJECT_ID = os.getenv("BROWSERBASE_PROJECT_ID")

# Timeout settings
SESSION_TIMEOUT = 30000  # 30 seconds
EXTRACTION_TIMEOUT = 15.0  # 15 seconds for httpx


class BrowserbaseError(Exception):
    """Custom exception for Browserbase errors"""
    pass


@weave.op()
async def create_browser_session() -> str:
    """Create a new Browserbase browser session"""
    async with httpx.AsyncClient(timeout=EXTRACTION_TIMEOUT) as client:
        response = await client.post(
            f"{BROWSERBASE_API_URL}/sessions",
            headers={
                "X-BB-API-Key": BROWSERBASE_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "projectId": BROWSERBASE_PROJECT_ID,
                "browserSettings": {
                    "blockAds": True,
                    "solveCaptchas": False
                }
            }
        )

        if response.status_code != 200 and response.status_code != 201:
            raise BrowserbaseError(f"Failed to create session: {response.text}")

        data = response.json()
        return data["id"]


async def close_browser_session(session_id: str) -> None:
    """Close a Browserbase session"""
    try:
        async with httpx.AsyncClient(timeout=EXTRACTION_TIMEOUT) as client:
            await client.post(
                f"{BROWSERBASE_API_URL}/sessions/{session_id}",
                headers={
                    "X-BB-API-Key": BROWSERBASE_API_KEY,
                    "Content-Type": "application/json"
                },
                json={
                    "status": "REQUEST_RELEASE",
                    "projectId": BROWSERBASE_PROJECT_ID
                }
            )
    except Exception as e:
        print(f"Error closing session {session_id}: {e}")


@weave.op()
async def extract_article_content(url: str, use_cache: bool = True) -> Optional[ArticleContent]:
    """
    Extract full article content from a URL using Browserbase.
    Returns structured ArticleContent or None if extraction fails.

    Args:
        url: The article URL to extract content from
        use_cache: Whether to check/use Redis cache (default True)
    """
    # Check cache first
    if use_cache:
        cached = await get_cached_article_content(url)
        if cached:
            return ArticleContent(
                url=cached.get("url", url),
                title=cached.get("title", ""),
                author=cached.get("author"),
                publication_date=cached.get("publication_date"),
                source_domain=cached.get("source_domain", ""),
                source_name=cached.get("source_name"),
                full_text=cached.get("full_text", ""),
                excerpt=cached.get("excerpt", "")
            )

    session_id = None
    try:
        print(f"[BROWSERBASE] Creating session for: {url}")
        session_id = await create_browser_session()
        print(f"[BROWSERBASE] Session created: {session_id}")

        # Get the session's CDP endpoint for browser automation
        async with httpx.AsyncClient(timeout=EXTRACTION_TIMEOUT) as client:
            # Navigate to URL and extract content using Browserbase's context API
            response = await client.post(
                f"{BROWSERBASE_API_URL}/sessions/{session_id}/browser/contexts/default/pages",
                headers={
                    "X-BB-API-Key": BROWSERBASE_API_KEY,
                    "Content-Type": "application/json"
                },
                json={"url": url}
            )

            if response.status_code not in [200, 201]:
                print(f"[BROWSERBASE ERROR] Page navigation failed: {response.status_code} - {response.text}")
                return None
            print(f"[BROWSERBASE] Page navigation success")

            page_data = response.json()
            page_id = page_data.get("id", "default")

            # Wait for page to load
            await asyncio.sleep(2)

            # Extract content using JavaScript evaluation
            extract_script = """
            () => {
                const getMetaContent = (name) => {
                    const meta = document.querySelector(`meta[name="${name}"], meta[property="${name}"], meta[property="og:${name}"]`);
                    return meta ? meta.getAttribute('content') : null;
                };

                const getArticleText = () => {
                    // Try common article selectors
                    const selectors = [
                        'article',
                        '[role="article"]',
                        '.article-body',
                        '.article-content',
                        '.post-content',
                        '.entry-content',
                        '.story-body',
                        'main'
                    ];

                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.textContent.length > 200) {
                            return el.textContent.trim();
                        }
                    }

                    // Fallback to body
                    return document.body.textContent.trim();
                };

                const getAuthor = () => {
                    const authorEl = document.querySelector('[rel="author"], .author, .byline, [class*="author"]');
                    if (authorEl) return authorEl.textContent.trim();
                    return getMetaContent('author');
                };

                const getDate = () => {
                    const timeEl = document.querySelector('time[datetime]');
                    if (timeEl) return timeEl.getAttribute('datetime');
                    const dateEl = document.querySelector('[class*="date"], [class*="published"]');
                    if (dateEl) return dateEl.textContent.trim();
                    return getMetaContent('article:published_time');
                };

                return {
                    title: document.title || getMetaContent('title') || '',
                    author: getAuthor(),
                    date: getDate(),
                    text: getArticleText(),
                    description: getMetaContent('description') || ''
                };
            }
            """

            eval_response = await client.post(
                f"{BROWSERBASE_API_URL}/sessions/{session_id}/browser/contexts/default/pages/{page_id}/evaluate",
                headers={
                    "X-BB-API-Key": BROWSERBASE_API_KEY,
                    "Content-Type": "application/json"
                },
                json={"expression": extract_script}
            )

            if eval_response.status_code != 200:
                # Fallback: return basic info
                parsed_url = urlparse(url)
                return ArticleContent(
                    url=url,
                    title="",
                    source_domain=parsed_url.netloc,
                    full_text="",
                    excerpt=""
                )

            result = eval_response.json().get("result", {})
            parsed_url = urlparse(url)

            full_text = result.get("text", "")

            article = ArticleContent(
                url=url,
                title=result.get("title", ""),
                author=result.get("author"),
                publication_date=result.get("date"),
                source_domain=parsed_url.netloc,
                source_name=parsed_url.netloc.replace("www.", ""),
                full_text=full_text,
                excerpt=full_text[:500] if full_text else ""
            )

            # Cache the extracted content
            if use_cache and full_text:
                await cache_article_content(url, {
                    "url": article.url,
                    "title": article.title,
                    "author": article.author,
                    "publication_date": article.publication_date,
                    "source_domain": article.source_domain,
                    "source_name": article.source_name,
                    "full_text": article.full_text,
                    "excerpt": article.excerpt
                })

            return article

    except Exception as e:
        print(f"[BROWSERBASE ERROR] Error extracting article: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        if session_id:
            try:
                await close_browser_session(session_id)
            except:
                pass


@weave.op()
async def search_news_sources(
    topic: str,
    exclude_domain: str,
    max_results: int = 5
) -> List[CrossReferenceResult]:
    """
    Search for the same news story across multiple sources.
    Uses DuckDuckGo News search as a simple fallback (no browser needed).
    """
    import time
    start_time = time.time()
    results = []
    search_source = "none"

    try:
        print(f"[NEWS_SEARCH] Searching for: {topic}")

        # Use DuckDuckGo News API (no auth required)
        search_query = topic.replace(" ", "+")
        search_url = f"https://duckduckgo.com/news.js?q={search_query}&o=json"

        async with httpx.AsyncClient(timeout=EXTRACTION_TIMEOUT) as client:
            # DuckDuckGo requires a browser-like user agent
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "application/json"
            }

            response = await client.get(search_url, headers=headers)
            print(f"[NEWS_SEARCH] DuckDuckGo response: {response.status_code}")

            if response.status_code == 200:
                try:
                    data = response.json()
                    articles = data.get("results", [])
                    print(f"[NEWS_SEARCH] Found {len(articles)} articles")
                    search_source = "duckduckgo"

                    for article in articles[:max_results]:
                        source_name = article.get("source", "Unknown")

                        # Skip if from excluded domain
                        if exclude_domain.lower() in source_name.lower():
                            continue

                        results.append(CrossReferenceResult(
                            source_url=article.get("url", ""),
                            source_name=source_name,
                            title=article.get("title", ""),
                            excerpt=article.get("excerpt", article.get("title", "")),
                            publication_date=article.get("date"),
                            relevance_score=0.8
                        ))
                except Exception as e:
                    print(f"[NEWS_SEARCH] Error parsing response: {e}")

        # If DuckDuckGo didn't work, try a simple Bing News search
        if not results:
            print(f"[NEWS_SEARCH] Trying Bing News fallback...")
            bing_url = f"https://www.bing.com/news/search?q={search_query}&format=rss"

            async with httpx.AsyncClient(timeout=EXTRACTION_TIMEOUT) as client:
                response = await client.get(bing_url, headers=headers)
                print(f"[NEWS_SEARCH] Bing response: {response.status_code}")

                if response.status_code == 200:
                    # Parse RSS feed
                    import re
                    items = re.findall(r'<item>(.*?)</item>', response.text, re.DOTALL)
                    print(f"[NEWS_SEARCH] Found {len(items)} Bing items")
                    search_source = "bing"

                    for item in items[:max_results]:
                        title_match = re.search(r'<title>(.*?)</title>', item)
                        link_match = re.search(r'<link>(.*?)</link>', item)
                        desc_match = re.search(r'<description>(.*?)</description>', item)

                        if title_match and link_match:
                            title = title_match.group(1)
                            link = link_match.group(1)
                            desc = desc_match.group(1) if desc_match else title

                            # Extract source from URL
                            source_domain = urlparse(link).netloc.replace("www.", "")

                            if exclude_domain.lower() in source_domain.lower():
                                continue

                            results.append(CrossReferenceResult(
                                source_url=link,
                                source_name=source_domain,
                                title=title,
                                excerpt=desc[:200] if desc else title,
                                relevance_score=0.7
                            ))

    except Exception as e:
        print(f"[NEWS_SEARCH ERROR] Error searching news sources: {e}")
        import traceback
        traceback.print_exc()

    # Log search metrics
    latency_ms = int((time.time() - start_time) * 1000)
    trace_news_search(
        query=topic,
        source=search_source if search_source != "none" else "fallback",
        results_count=len(results),
        success=len(results) > 0,
        latency_ms=latency_ms
    )

    print(f"[NEWS_SEARCH] Returning {len(results)} results")
    return results


@weave.op()
async def fetch_url_preview(url: str) -> dict:
    """
    Fetch a rich preview for a URL.
    This is the existing preview endpoint implementation.
    """
    try:
        content = await extract_article_content(url)

        if content:
            return {
                "title": content.title,
                "summary": content.excerpt,
                "author": content.author,
                "published_date": content.publication_date,
                "source": content.source_name,
                "url": url
            }

        return {
            "title": "",
            "summary": "",
            "author": None,
            "published_date": None,
            "source": urlparse(url).netloc,
            "url": url
        }

    except Exception as e:
        print(f"Error fetching preview: {e}")
        return {
            "title": "",
            "summary": "",
            "error": str(e),
            "url": url
        }


async def fetch_cross_reference_content(
    cross_refs: List[CrossReferenceResult],
    max_concurrent: int = 3
) -> List[CrossReferenceResult]:
    """
    Fetch full content for cross-reference results.
    Uses semaphore to limit concurrent requests.
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_one(ref: CrossReferenceResult) -> CrossReferenceResult:
        async with semaphore:
            try:
                content = await extract_article_content(ref.source_url)
                if content:
                    ref.full_text = content.full_text
                    ref.excerpt = content.excerpt
            except:
                pass
            return ref

    results = await asyncio.gather(
        *[fetch_one(ref) for ref in cross_refs],
        return_exceptions=True
    )

    return [r for r in results if isinstance(r, CrossReferenceResult)]
