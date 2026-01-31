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


@weave.op()
async def close_browser_session(session_id: str) -> None:
    """Close a Browserbase session"""
    async with httpx.AsyncClient(timeout=EXTRACTION_TIMEOUT) as client:
        await client.post(
            f"{BROWSERBASE_API_URL}/sessions/{session_id}/close",
            headers={"X-BB-API-Key": BROWSERBASE_API_KEY}
        )


@weave.op()
async def extract_article_content(url: str) -> Optional[ArticleContent]:
    """
    Extract full article content from a URL using Browserbase.
    Returns structured ArticleContent or None if extraction fails.
    """
    session_id = None
    try:
        session_id = await create_browser_session()

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
                return None

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

            return ArticleContent(
                url=url,
                title=result.get("title", ""),
                author=result.get("author"),
                publication_date=result.get("date"),
                source_domain=parsed_url.netloc,
                source_name=parsed_url.netloc.replace("www.", ""),
                full_text=full_text,
                excerpt=full_text[:500] if full_text else ""
            )

    except Exception as e:
        print(f"Error extracting article: {e}")
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
    Uses Google News search via Browserbase.
    """
    session_id = None
    results = []

    try:
        session_id = await create_browser_session()

        # Search Google News
        search_query = topic.replace(" ", "+")
        search_url = f"https://news.google.com/search?q={search_query}&hl=en-US&gl=US&ceid=US:en"

        async with httpx.AsyncClient(timeout=EXTRACTION_TIMEOUT) as client:
            # Navigate to search
            response = await client.post(
                f"{BROWSERBASE_API_URL}/sessions/{session_id}/browser/contexts/default/pages",
                headers={
                    "X-BB-API-Key": BROWSERBASE_API_KEY,
                    "Content-Type": "application/json"
                },
                json={"url": search_url}
            )

            if response.status_code not in [200, 201]:
                return results

            page_data = response.json()
            page_id = page_data.get("id", "default")

            # Wait for results to load
            await asyncio.sleep(3)

            # Extract search results
            extract_script = f"""
            () => {{
                const results = [];
                const articles = document.querySelectorAll('article');
                const excludeDomain = "{exclude_domain}".toLowerCase();

                for (const article of articles) {{
                    if (results.length >= {max_results}) break;

                    const linkEl = article.querySelector('a[href^="./articles/"]');
                    const titleEl = article.querySelector('h3, h4');
                    const sourceEl = article.querySelector('[data-n-tid], .source');
                    const timeEl = article.querySelector('time');

                    if (linkEl && titleEl) {{
                        const sourceName = sourceEl ? sourceEl.textContent.trim() : 'Unknown';

                        // Skip if from excluded domain
                        if (sourceName.toLowerCase().includes(excludeDomain)) continue;

                        results.push({{
                            title: titleEl.textContent.trim(),
                            source: sourceName,
                            time: timeEl ? timeEl.textContent.trim() : '',
                            href: linkEl.href
                        }});
                    }}
                }}

                return results;
            }}
            """

            eval_response = await client.post(
                f"{BROWSERBASE_API_URL}/sessions/{session_id}/browser/contexts/default/pages/{page_id}/evaluate",
                headers={
                    "X-BB-API-Key": BROWSERBASE_API_KEY,
                    "Content-Type": "application/json"
                },
                json={"expression": extract_script}
            )

            if eval_response.status_code == 200:
                search_results = eval_response.json().get("result", [])

                for item in search_results[:max_results]:
                    results.append(CrossReferenceResult(
                        source_url=item.get("href", ""),
                        source_name=item.get("source", "Unknown"),
                        title=item.get("title", ""),
                        excerpt=item.get("title", ""),  # Use title as excerpt initially
                        publication_date=item.get("time"),
                        relevance_score=0.8  # Default relevance
                    ))

    except Exception as e:
        print(f"Error searching news sources: {e}")
    finally:
        if session_id:
            try:
                await close_browser_session(session_id)
            except:
                pass

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
