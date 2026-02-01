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

# Google Fact Check API (free, no key required for basic usage)
GOOGLE_FACT_CHECK_API = "https://factchecktools.googleapis.com/v1alpha1/claims:search"
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Timeout settings
SESSION_TIMEOUT = 30000  # 30 seconds
EXTRACTION_TIMEOUT = 15.0  # 15 seconds for httpx

# Trusted fact-checking sources with credibility scores
FACT_CHECK_SOURCES = {
    "snopes.com": {"name": "Snopes", "credibility": 0.95, "type": "fact_checker"},
    "politifact.com": {"name": "PolitiFact", "credibility": 0.95, "type": "fact_checker"},
    "factcheck.org": {"name": "FactCheck.org", "credibility": 0.95, "type": "fact_checker"},
    "apnews.com": {"name": "Associated Press", "credibility": 0.95, "type": "news_wire"},
    "reuters.com": {"name": "Reuters", "credibility": 0.95, "type": "news_wire"},
    "bbc.com": {"name": "BBC", "credibility": 0.90, "type": "news_outlet"},
    "npr.org": {"name": "NPR", "credibility": 0.90, "type": "news_outlet"},
    "fullfact.org": {"name": "Full Fact", "credibility": 0.90, "type": "fact_checker"},
    "leadstories.com": {"name": "Lead Stories", "credibility": 0.85, "type": "fact_checker"},
    "verifythis.com": {"name": "VERIFY", "credibility": 0.85, "type": "fact_checker"},
}

def get_source_credibility(url: str) -> tuple[str, float, str]:
    """Get credibility score for a source based on its domain."""
    from urllib.parse import urlparse
    domain = urlparse(url).netloc.replace("www.", "").lower()

    for source_domain, info in FACT_CHECK_SOURCES.items():
        if source_domain in domain:
            return info["name"], info["credibility"], info["type"]

    # Default credibility for unknown sources
    return domain, 0.5, "unknown"


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

            # If Browserbase returned empty content, try HTTP fallback
            if not full_text:
                print(f"[BROWSERBASE] Empty content, trying HTTP fallback for: {url}")
                return await extract_article_simple(url, use_cache)

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
        # Try HTTP fallback
        print(f"[FALLBACK] Trying simple HTTP extraction for: {url}")
        return await extract_article_simple(url, use_cache)
    finally:
        if session_id:
            try:
                await close_browser_session(session_id)
            except:
                pass


async def extract_article_simple(url: str, use_cache: bool = True) -> Optional[ArticleContent]:
    """
    Simple HTTP-based article extraction fallback.
    Uses basic HTML parsing when Browserbase is unavailable.
    """
    import re

    try:
        print(f"[HTTP FALLBACK] Fetching: {url}")
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            response = await client.get(url, headers=headers)

            if response.status_code != 200:
                print(f"[HTTP FALLBACK] Failed with status: {response.status_code}")
                return None

            html = response.text
            parsed_url = urlparse(url)

            # Extract title
            title_match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.IGNORECASE)
            title = title_match.group(1).strip() if title_match else ""

            # Extract meta description
            desc_match = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
            if not desc_match:
                desc_match = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description["\']', html, re.IGNORECASE)
            description = desc_match.group(1).strip() if desc_match else ""

            # Extract author
            author_match = re.search(r'<meta[^>]+name=["\']author["\'][^>]+content=["\']([^"\']+)["\']', html, re.IGNORECASE)
            author = author_match.group(1).strip() if author_match else None

            # Extract article text - try common patterns
            # Remove scripts and styles first
            html_clean = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html_clean = re.sub(r'<style[^>]*>.*?</style>', '', html_clean, flags=re.DOTALL | re.IGNORECASE)

            # Try to find article content
            article_match = re.search(r'<article[^>]*>(.*?)</article>', html_clean, re.DOTALL | re.IGNORECASE)
            if article_match:
                article_html = article_match.group(1)
            else:
                # Try main tag
                main_match = re.search(r'<main[^>]*>(.*?)</main>', html_clean, re.DOTALL | re.IGNORECASE)
                if main_match:
                    article_html = main_match.group(1)
                else:
                    # Use body as fallback
                    body_match = re.search(r'<body[^>]*>(.*?)</body>', html_clean, re.DOTALL | re.IGNORECASE)
                    article_html = body_match.group(1) if body_match else html_clean

            # Extract paragraphs
            paragraphs = re.findall(r'<p[^>]*>([^<]+(?:<[^>]+>[^<]+)*)</p>', article_html, re.IGNORECASE)

            # Clean HTML tags from paragraphs
            clean_paragraphs = []
            for p in paragraphs:
                clean_text = re.sub(r'<[^>]+>', '', p).strip()
                if len(clean_text) > 50:  # Filter out short snippets
                    clean_paragraphs.append(clean_text)

            full_text = '\n\n'.join(clean_paragraphs)

            if not full_text and description:
                full_text = description

            print(f"[HTTP FALLBACK] Extracted {len(full_text)} chars, title: {title[:50]}...")

            if full_text:
                article = ArticleContent(
                    url=url,
                    title=title,
                    author=author,
                    publication_date=None,
                    source_domain=parsed_url.netloc,
                    source_name=parsed_url.netloc.replace("www.", ""),
                    full_text=full_text,
                    excerpt=full_text[:500] if full_text else ""
                )

                # Cache the result
                if use_cache:
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

            return None

    except Exception as e:
        print(f"[HTTP FALLBACK ERROR] {e}")
        return None


@weave.op()
async def search_google_fact_check(
    query: str,
    max_results: int = 5
) -> List[CrossReferenceResult]:
    """
    Search Google Fact Check Explorer API for existing fact checks.
    This aggregates results from Snopes, PolitiFact, FactCheck.org, and other
    IFCN-certified fact-checkers.
    """
    results = []

    try:
        print(f"[FACT_CHECK] Searching Google Fact Check API for: {query[:50]}...")

        # Google Fact Check Tools API
        params = {
            "query": query,
            "languageCode": "en",
        }
        if GOOGLE_API_KEY:
            params["key"] = GOOGLE_API_KEY

        async with httpx.AsyncClient(timeout=EXTRACTION_TIMEOUT) as client:
            response = await client.get(GOOGLE_FACT_CHECK_API, params=params)
            print(f"[FACT_CHECK] Google API response: {response.status_code}")

            if response.status_code == 200:
                data = response.json()
                claims = data.get("claims", [])
                print(f"[FACT_CHECK] Found {len(claims)} fact-check claims")

                for claim in claims[:max_results]:
                    claim_review = claim.get("claimReview", [{}])[0]
                    publisher = claim_review.get("publisher", {})
                    source_url = claim_review.get("url", "")
                    source_name, credibility, source_type = get_source_credibility(source_url)

                    results.append(CrossReferenceResult(
                        source_url=source_url,
                        source_name=publisher.get("name", source_name),
                        title=claim_review.get("title", claim.get("text", "")),
                        excerpt=f"Rating: {claim_review.get('textualRating', 'Unknown')}. {claim.get('text', '')}",
                        publication_date=claim_review.get("reviewDate"),
                        relevance_score=credibility,
                        full_text=claim.get("text", ""),
                        source_type=source_type
                    ))

    except Exception as e:
        print(f"[FACT_CHECK ERROR] Google Fact Check API error: {e}")

    return results


@weave.op()
async def search_snopes(query: str, max_results: int = 3) -> List[CrossReferenceResult]:
    """Search Snopes.com for fact checks using RSS feed with keyword filtering."""
    results = []
    try:
        import re
        # Fetch Snopes RSS feed and filter by query keywords
        rss_url = "https://www.snopes.com/feed/"
        print(f"[SNOPES] Fetching RSS feed, filtering for: {query[:50]}...")

        async with httpx.AsyncClient(timeout=EXTRACTION_TIMEOUT, follow_redirects=True) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "application/rss+xml,application/xml",
            }
            response = await client.get(rss_url, headers=headers)
            print(f"[SNOPES] RSS response status: {response.status_code}")

            if response.status_code == 200:
                # Parse RSS items
                items = re.findall(r'<item>(.*?)</item>', response.text, re.DOTALL)
                print(f"[SNOPES] Found {len(items)} RSS items")

                # Extract keywords from query (lowercase)
                query_words = set(query.lower().split())

                matched_items = []
                for item in items:
                    title_match = re.search(r'<title><!\[CDATA\[(.*?)\]\]></title>', item)
                    link_match = re.search(r'<link>(.*?)</link>', item)
                    desc_match = re.search(r'<description><!\[CDATA\[(.*?)\]\]></description>', item)

                    if title_match and link_match:
                        title = title_match.group(1)
                        link = link_match.group(1)
                        desc = desc_match.group(1) if desc_match else ""

                        # Check if any query words are in title or description
                        combined_text = (title + " " + desc).lower()
                        matching_words = sum(1 for word in query_words if word in combined_text)

                        if matching_words >= 1:  # At least 1 keyword match
                            matched_items.append({
                                "url": link,
                                "title": title,
                                "desc": desc,
                                "score": matching_words
                            })

                # Sort by matching score (more keyword matches = better)
                matched_items.sort(key=lambda x: x["score"], reverse=True)
                print(f"[SNOPES] Found {len(matched_items)} matching items")

                for item in matched_items[:max_results]:
                    results.append(CrossReferenceResult(
                        source_url=item["url"],
                        source_name="Snopes",
                        title=item["title"],
                        excerpt=f"Snopes: {item['desc'][:200]}",
                        relevance_score=0.95,
                        source_type="fact_checker"
                    ))

    except Exception as e:
        print(f"[SNOPES ERROR] {e}")
        import traceback
        traceback.print_exc()

    return results


@weave.op()
async def search_politifact(query: str, max_results: int = 3) -> List[CrossReferenceResult]:
    """Search PolitiFact for fact checks."""
    results = []
    try:
        from urllib.parse import quote_plus
        search_url = f"https://www.politifact.com/search/?q={quote_plus(query)}"
        print(f"[POLITIFACT] Searching: {query[:50]}...")

        async with httpx.AsyncClient(timeout=EXTRACTION_TIMEOUT, follow_redirects=True) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9"
            }
            response = await client.get(search_url, headers=headers)
            print(f"[POLITIFACT] Response status: {response.status_code}")

            if response.status_code == 200:
                import re
                # Multiple patterns for different PolitiFact layouts
                patterns = [
                    r'href="(https://www\.politifact\.com/factchecks/[^"]+)"[^>]*>([^<]+)',
                    r'<a[^>]+href="(/factchecks/[^"]+)"[^>]*>([^<]+)</a>',
                    r'class="[^"]*statement[^"]*"[^>]*>.*?<a[^>]+href="(/factchecks/[^"]+)"[^>]*>([^<]+)',
                ]

                all_matches = []
                for pattern in patterns:
                    matches = re.findall(pattern, response.text, re.IGNORECASE | re.DOTALL)
                    for path, title in matches:
                        # Normalize path
                        if not path.startswith("http"):
                            path = f"https://www.politifact.com{path}"
                        all_matches.append((path, title))

                # Deduplicate
                seen = set()
                unique_matches = []
                for url, title in all_matches:
                    title_clean = title.strip()
                    if url not in seen and len(title_clean) > 10:
                        seen.add(url)
                        unique_matches.append((url, title_clean))

                print(f"[POLITIFACT] Found {len(unique_matches)} results")

                for url, title in unique_matches[:max_results]:
                    results.append(CrossReferenceResult(
                        source_url=url,
                        source_name="PolitiFact",
                        title=title,
                        excerpt=f"Fact check from PolitiFact: {title}",
                        relevance_score=0.95,
                        source_type="fact_checker"
                    ))

    except Exception as e:
        print(f"[POLITIFACT ERROR] {e}")
        import traceback
        traceback.print_exc()

    return results


@weave.op()
async def search_factcheck_org(query: str, max_results: int = 3) -> List[CrossReferenceResult]:
    """Search FactCheck.org for fact checks using WordPress REST API."""
    results = []
    try:
        from urllib.parse import quote_plus
        # Use WordPress REST API for search
        search_url = f"https://www.factcheck.org/wp-json/wp/v2/posts?search={quote_plus(query)}&per_page={max_results}"
        print(f"[FACTCHECK.ORG] Searching via API: {query[:50]}...")

        async with httpx.AsyncClient(timeout=EXTRACTION_TIMEOUT, follow_redirects=True) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "application/json",
            }
            response = await client.get(search_url, headers=headers)
            print(f"[FACTCHECK.ORG] API response status: {response.status_code}")

            if response.status_code == 200:
                posts = response.json()
                print(f"[FACTCHECK.ORG] Found {len(posts)} results")

                for post in posts[:max_results]:
                    # Clean HTML from title
                    import re
                    title = re.sub(r'<[^>]+>', '', post.get("title", {}).get("rendered", ""))
                    excerpt = re.sub(r'<[^>]+>', '', post.get("excerpt", {}).get("rendered", ""))

                    results.append(CrossReferenceResult(
                        source_url=post.get("link", ""),
                        source_name="FactCheck.org",
                        title=title.strip(),
                        excerpt=f"Fact check: {excerpt[:200].strip()}",
                        publication_date=post.get("date"),
                        relevance_score=0.95,
                        source_type="fact_checker"
                    ))

    except Exception as e:
        print(f"[FACTCHECK.ORG ERROR] {e}")

    return results


@weave.op()
async def search_ap_reuters(query: str, max_results: int = 3) -> List[CrossReferenceResult]:
    """Search AP News and Reuters for corroborating news coverage."""
    results = []

    # Search AP News
    try:
        from urllib.parse import quote_plus
        ap_url = f"https://apnews.com/search?q={quote_plus(query)}"
        print(f"[AP/REUTERS] Searching AP News: {query[:50]}...")

        async with httpx.AsyncClient(timeout=EXTRACTION_TIMEOUT, follow_redirects=True) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "text/html"
            }
            response = await client.get(ap_url, headers=headers)

            if response.status_code == 200:
                import re
                # Extract article links
                articles = re.findall(
                    r'<a[^>]+href="(https://apnews\.com/article/[^"]+)"[^>]*>([^<]+)</a>',
                    response.text
                )
                print(f"[AP] Found {len(articles)} results")

                for url, title in articles[:max_results]:
                    if len(title.strip()) > 10:
                        results.append(CrossReferenceResult(
                            source_url=url,
                            source_name="Associated Press",
                            title=title.strip(),
                            excerpt=f"AP News: {title.strip()}",
                            relevance_score=0.95,
                            source_type="news_wire"
                        ))

    except Exception as e:
        print(f"[AP ERROR] {e}")

    # Search Reuters
    try:
        reuters_url = f"https://www.reuters.com/search/news?query={query.replace(' ', '+')}"
        print(f"[REUTERS] Searching: {query[:50]}...")

        async with httpx.AsyncClient(timeout=EXTRACTION_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(reuters_url, headers=headers)

            if response.status_code == 200:
                import re
                articles = re.findall(
                    r'<a[^>]+href="(/[^"]+article[^"]+)"[^>]*>.*?<h3[^>]*>([^<]+)</h3>',
                    response.text,
                    re.DOTALL
                )
                print(f"[REUTERS] Found {len(articles)} results")

                for path, title in articles[:max_results]:
                    if len(title.strip()) > 10:
                        results.append(CrossReferenceResult(
                            source_url=f"https://www.reuters.com{path}",
                            source_name="Reuters",
                            title=title.strip(),
                            excerpt=f"Reuters: {title.strip()}",
                            relevance_score=0.95,
                            source_type="news_wire"
                        ))

    except Exception as e:
        print(f"[REUTERS ERROR] {e}")

    return results


@weave.op()
async def search_news_sources(
    topic: str,
    exclude_domain: str,
    max_results: int = 5
) -> List[CrossReferenceResult]:
    """
    Search for fact checks and corroborating sources using trusted fact-checkers.

    Priority order:
    1. Google Fact Check Explorer (aggregates Snopes, PolitiFact, FactCheck.org, etc.)
    2. Direct Snopes search
    3. Direct PolitiFact search
    4. AP News and Reuters (news wire services)

    Falls back to general news search if fact-checkers return no results.
    """
    import time
    start_time = time.time()
    all_results = []
    sources_used = []

    print(f"[NEWS_SEARCH] Searching trusted sources for: {topic[:80]}...")

    # Run fact-checker searches in parallel for speed
    search_tasks = [
        search_google_fact_check(topic, max_results=3),
        search_snopes(topic, max_results=2),
        search_politifact(topic, max_results=2),
        search_factcheck_org(topic, max_results=2),
        search_ap_reuters(topic, max_results=3),
    ]

    try:
        results_list = await asyncio.gather(*search_tasks, return_exceptions=True)

        # Collect results from each source
        source_names = ["Google Fact Check", "Snopes", "PolitiFact", "FactCheck.org", "AP/Reuters"]
        for i, results in enumerate(results_list):
            if isinstance(results, list) and results:
                sources_used.append(source_names[i])
                for r in results:
                    # Skip if from excluded domain
                    if exclude_domain.lower() in r.source_url.lower():
                        continue
                    all_results.append(r)

        print(f"[NEWS_SEARCH] Sources used: {sources_used}")
        print(f"[NEWS_SEARCH] Total results before dedup: {len(all_results)}")

        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        for r in all_results:
            if r.source_url not in seen_urls:
                seen_urls.add(r.source_url)
                unique_results.append(r)

        # Sort by credibility score (highest first)
        unique_results.sort(key=lambda x: x.relevance_score, reverse=True)

        # Limit to max_results
        all_results = unique_results[:max_results]

    except Exception as e:
        print(f"[NEWS_SEARCH ERROR] Error in parallel search: {e}")
        import traceback
        traceback.print_exc()

    # Fallback to general news search if no fact-check results
    if not all_results:
        print(f"[NEWS_SEARCH] No fact-check results, trying general news search...")
        all_results = await _search_general_news(topic, exclude_domain, max_results)
        if all_results:
            sources_used.append("General News")

    # Log search metrics
    latency_ms = int((time.time() - start_time) * 1000)
    trace_news_search(
        query=topic,
        source=",".join(sources_used) if sources_used else "none",
        results_count=len(all_results),
        success=len(all_results) > 0,
        latency_ms=latency_ms
    )

    print(f"[NEWS_SEARCH] Returning {len(all_results)} verified results from: {sources_used}")
    return all_results


async def _search_general_news(
    topic: str,
    exclude_domain: str,
    max_results: int = 5
) -> List[CrossReferenceResult]:
    """
    Fallback general news search using Bing News RSS.
    Only used when fact-checkers return no results.
    """
    results = []
    search_query = topic.replace(" ", "+")

    try:
        print(f"[GENERAL_NEWS] Trying Bing News RSS fallback...")
        bing_url = f"https://www.bing.com/news/search?q={search_query}&format=rss"

        async with httpx.AsyncClient(timeout=EXTRACTION_TIMEOUT) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "application/rss+xml"
            }
            response = await client.get(bing_url, headers=headers)
            print(f"[GENERAL_NEWS] Bing response: {response.status_code}")

            if response.status_code == 200:
                import re
                items = re.findall(r'<item>(.*?)</item>', response.text, re.DOTALL)
                print(f"[GENERAL_NEWS] Found {len(items)} Bing items")

                for item in items[:max_results * 2]:  # Get more, filter later
                    title_match = re.search(r'<title>(.*?)</title>', item)
                    link_match = re.search(r'<link>(.*?)</link>', item)
                    desc_match = re.search(r'<description>(.*?)</description>', item)

                    if title_match and link_match:
                        title = title_match.group(1)
                        link = link_match.group(1)
                        desc = desc_match.group(1) if desc_match else title

                        # Get source credibility
                        source_name, credibility, source_type = get_source_credibility(link)

                        # Skip excluded domain
                        if exclude_domain.lower() in link.lower():
                            continue

                        results.append(CrossReferenceResult(
                            source_url=link,
                            source_name=source_name,
                            title=title,
                            excerpt=desc[:200] if desc else title,
                            relevance_score=credibility,
                            source_type=source_type
                        ))

                        if len(results) >= max_results:
                            break

    except Exception as e:
        print(f"[GENERAL_NEWS ERROR] {e}")

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
