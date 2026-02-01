"""
Stress test for article caching performance.
Compares first-time fetch vs cached retrieval times.
"""

import asyncio
import time
import random
import string
from typing import List, Tuple
import statistics

# Add current directory to path
import sys
sys.path.insert(0, '.')


def generate_random_urls(count: int = 50) -> List[str]:
    """Generate random unique URLs for testing."""
    domains = [
        "news.example.com", "tech.daily.com", "world.times.org",
        "business.herald.net", "science.today.io", "sports.gazette.com",
        "politics.wire.org", "health.journal.net", "culture.review.io"
    ]

    urls = []
    for i in range(count):
        domain = random.choice(domains)
        slug = ''.join(random.choices(string.ascii_lowercase, k=10))
        urls.append(f"https://{domain}/article/{slug}-{i}")

    return urls


def generate_mock_article(url: str) -> dict:
    """Generate mock article content for a URL."""
    words = ["technology", "innovation", "research", "development", "breakthrough",
             "scientists", "discovered", "announced", "reported", "analysis"]

    title = f"Breaking: {' '.join(random.choices(words, k=5)).title()}"
    full_text = ' '.join(random.choices(words, k=200))

    return {
        "url": url,
        "title": title,
        "author": f"Author {random.randint(1, 100)}",
        "publication_date": "2024-01-31",
        "source_domain": url.split('/')[2],
        "source_name": url.split('/')[2].replace('.', ' ').title(),
        "full_text": full_text,
        "excerpt": full_text[:500]
    }


async def run_stress_test(num_urls: int = 50):
    """Run the stress test comparing cached vs uncached performance."""

    from services.redis_client import (
        init_redis,
        cache_article_content,
        get_cached_article_content,
        get_article_cache_stats,
        get_redis
    )

    print(f"\n{'='*60}")
    print(f"ARTICLE CACHE STRESS TEST - {num_urls} URLs")
    print(f"{'='*60}\n")

    # Initialize Redis
    await init_redis()

    # Clear existing test articles
    redis = await get_redis()
    if redis:
        keys = await redis.keys("article:*")
        if keys:
            await redis.delete(*keys)
            print(f"Cleared {len(keys)} existing cached articles\n")

    # Generate test URLs
    urls = generate_random_urls(num_urls)
    print(f"Generated {len(urls)} unique test URLs\n")

    # ==========================================
    # FIRST PASS: Simulate fetch + cache (no cache hits)
    # ==========================================
    print(f"{'='*60}")
    print("FIRST PASS: Simulating article fetch + cache write")
    print(f"{'='*60}")

    first_pass_times: List[float] = []

    start_total = time.time()
    for i, url in enumerate(urls):
        start = time.time()

        # Check cache (should miss)
        cached = await get_cached_article_content(url)

        if cached is None:
            # Simulate fetch delay (Browserbase typically takes 2-5 seconds)
            await asyncio.sleep(0.05)  # 50ms simulated fetch time

            # Generate mock content
            content = generate_mock_article(url)

            # Cache it
            await cache_article_content(url, content)

        elapsed = (time.time() - start) * 1000  # ms
        first_pass_times.append(elapsed)

        if (i + 1) % 10 == 0:
            print(f"  Processed {i + 1}/{num_urls} URLs...")

    first_pass_total = time.time() - start_total

    print(f"\nFirst pass complete!")
    print(f"  Total time: {first_pass_total:.2f}s")
    print(f"  Avg per URL: {statistics.mean(first_pass_times):.2f}ms")
    print(f"  Min: {min(first_pass_times):.2f}ms, Max: {max(first_pass_times):.2f}ms")

    # Check cache stats
    stats = await get_article_cache_stats()
    print(f"  Cached articles: {stats.get('cached_articles', 0)}")

    # ==========================================
    # SECOND PASS: Cache hits only
    # ==========================================
    print(f"\n{'='*60}")
    print("SECOND PASS: Reading from cache (should be fast)")
    print(f"{'='*60}")

    second_pass_times: List[float] = []
    cache_hits = 0
    cache_misses = 0

    start_total = time.time()
    for i, url in enumerate(urls):
        start = time.time()

        # Check cache (should hit)
        cached = await get_cached_article_content(url)

        if cached:
            cache_hits += 1
        else:
            cache_misses += 1

        elapsed = (time.time() - start) * 1000  # ms
        second_pass_times.append(elapsed)

    second_pass_total = time.time() - start_total

    print(f"\nSecond pass complete!")
    print(f"  Total time: {second_pass_total:.2f}s")
    print(f"  Avg per URL: {statistics.mean(second_pass_times):.2f}ms")
    print(f"  Min: {min(second_pass_times):.2f}ms, Max: {max(second_pass_times):.2f}ms")
    print(f"  Cache hits: {cache_hits}, Cache misses: {cache_misses}")

    # ==========================================
    # THIRD PASS: Concurrent cache reads
    # ==========================================
    print(f"\n{'='*60}")
    print("THIRD PASS: Concurrent cache reads (all at once)")
    print(f"{'='*60}")

    async def fetch_one(url: str) -> Tuple[str, float]:
        start = time.time()
        await get_cached_article_content(url)
        return url, (time.time() - start) * 1000

    start_total = time.time()
    results = await asyncio.gather(*[fetch_one(url) for url in urls])
    third_pass_total = time.time() - start_total
    third_pass_times = [r[1] for r in results]

    print(f"\nThird pass complete!")
    print(f"  Total time: {third_pass_total:.2f}s")
    print(f"  Avg per URL: {statistics.mean(third_pass_times):.2f}ms")
    print(f"  Min: {min(third_pass_times):.2f}ms, Max: {max(third_pass_times):.2f}ms")

    # ==========================================
    # SUMMARY
    # ==========================================
    print(f"\n{'='*60}")
    print("PERFORMANCE SUMMARY")
    print(f"{'='*60}")

    speedup = statistics.mean(first_pass_times) / statistics.mean(second_pass_times)

    print(f"""
    URLs tested:        {num_urls}

    First pass (fetch + cache):
      Total:            {first_pass_total:.2f}s
      Avg per URL:      {statistics.mean(first_pass_times):.2f}ms

    Second pass (cache reads, sequential):
      Total:            {second_pass_total:.2f}s
      Avg per URL:      {statistics.mean(second_pass_times):.2f}ms

    Third pass (cache reads, concurrent):
      Total:            {third_pass_total:.2f}s
      Avg per URL:      {statistics.mean(third_pass_times):.2f}ms

    SPEEDUP (cache vs fetch): {speedup:.1f}x faster
    TIME SAVED per request:   {statistics.mean(first_pass_times) - statistics.mean(second_pass_times):.2f}ms
    """)

    # Cleanup
    if redis:
        keys = await redis.keys("article:*")
        if keys:
            await redis.delete(*keys)
            print(f"Cleaned up {len(keys)} test articles from cache")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Stress test article caching")
    parser.add_argument("--urls", type=int, default=50, help="Number of URLs to test")
    args = parser.parse_args()

    asyncio.run(run_stress_test(args.urls))
