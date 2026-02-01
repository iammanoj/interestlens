"""
Stress test for authenticity API with real news URLs.
Tests verification status across multiple requests.
"""

import asyncio
import time
import httpx
import random
import json
from typing import List, Dict
from collections import Counter

# Sample news URLs from various sources for testing
NEWS_URLS = [
    "https://www.reuters.com/world/",
    "https://www.bbc.com/news",
    "https://www.cnn.com/politics",
    "https://www.nytimes.com/section/politics",
    "https://www.washingtonpost.com/politics/",
    "https://www.theguardian.com/us-news",
    "https://www.foxnews.com/politics",
    "https://www.nbcnews.com/politics",
    "https://www.cbsnews.com/politics/",
    "https://www.usatoday.com/news/politics/",
    "https://apnews.com/politics",
    "https://www.politico.com/",
    "https://thehill.com/",
    "https://www.axios.com/politics",
    "https://www.npr.org/sections/politics/",
]

# Sample article texts for testing (when URL extraction fails)
SAMPLE_TEXTS = [
    "President Biden announced new economic policies today at the White House. The measures include tax reforms and infrastructure spending. Treasury Secretary confirmed the plans during a press briefing.",
    "Scientists at MIT discovered a breakthrough in renewable energy technology. The new solar panel design achieves 40% efficiency, breaking previous records. The research was published in Nature journal.",
    "The Federal Reserve raised interest rates by 0.25% in their latest meeting. Chair Powell cited inflation concerns as the primary driver. Markets reacted with mixed results.",
    "Apple unveiled its latest iPhone model featuring AI-powered features. CEO Tim Cook demonstrated the new capabilities at the company's headquarters in Cupertino.",
    "Climate activists gathered in Washington DC demanding stronger environmental policies. Organizers estimate over 50,000 participants attended the rally.",
    "SpaceX successfully launched its Starship rocket from Texas. Elon Musk announced plans for Mars missions within the next decade.",
    "The Supreme Court issued a major ruling on voting rights today. The 6-3 decision impacts election procedures in several states.",
    "Amazon reported record quarterly earnings, exceeding analyst expectations. CEO Andy Jassy attributed growth to cloud computing services.",
    "NATO leaders met in Brussels to discuss defense spending commitments. Secretary General emphasized the importance of collective security.",
    "A new study published in The Lancet reveals promising results for cancer treatment. Researchers at Johns Hopkins conducted the clinical trials.",
]


async def check_authenticity(client: httpx.AsyncClient, url: str, text: str, item_id: str) -> Dict:
    """Call the authenticity API and return the result."""
    try:
        response = await client.post(
            "http://localhost:8000/check_authenticity",
            json={
                "item_id": item_id,
                "url": url,
                "text": text,
                "check_depth": "quick"
            },
            timeout=120.0
        )
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"HTTP {response.status_code}", "verification_status": "error"}
    except Exception as e:
        return {"error": str(e), "verification_status": "error"}


async def run_stress_test(num_requests: int = 100, max_concurrent: int = 5):
    """Run stress test with specified number of requests."""

    print(f"\n{'='*60}")
    print(f"AUTHENTICITY API STRESS TEST - {num_requests} requests")
    print(f"Max concurrent: {max_concurrent}")
    print(f"{'='*60}\n")

    results = []
    semaphore = asyncio.Semaphore(max_concurrent)

    async with httpx.AsyncClient() as client:
        async def process_one(i: int) -> Dict:
            async with semaphore:
                # Pick a random URL and text
                url = random.choice(NEWS_URLS)
                text = random.choice(SAMPLE_TEXTS)
                item_id = f"stress-test-{i}-{int(time.time())}"

                start = time.time()
                result = await check_authenticity(client, url, text, item_id)
                elapsed = time.time() - start

                result["request_id"] = i
                result["elapsed_seconds"] = elapsed
                result["url"] = url

                status = result.get("verification_status", "unknown")
                print(f"  [{i+1:3d}/{num_requests}] {status:20s} ({elapsed:.1f}s) - {url[:40]}...")

                return result

        print("Starting requests...\n")
        start_time = time.time()

        # Run all requests with concurrency limit
        tasks = [process_one(i) for i in range(num_requests)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        total_time = time.time() - start_time

    # Filter out exceptions
    valid_results = [r for r in results if isinstance(r, dict)]
    errors = [r for r in results if not isinstance(r, dict)]

    # Count verification statuses
    status_counts = Counter(r.get("verification_status", "unknown") for r in valid_results)

    # Calculate statistics
    processing_times = [r.get("processing_time_ms", 0) for r in valid_results if "processing_time_ms" in r]
    elapsed_times = [r.get("elapsed_seconds", 0) for r in valid_results if "elapsed_seconds" in r]

    avg_processing = sum(processing_times) / len(processing_times) if processing_times else 0
    avg_elapsed = sum(elapsed_times) / len(elapsed_times) if elapsed_times else 0

    # Print results
    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")

    print(f"\nTotal requests:     {num_requests}")
    print(f"Successful:         {len(valid_results)}")
    print(f"Errors:             {len(errors)}")
    print(f"Total time:         {total_time:.1f}s")
    print(f"Avg time/request:   {avg_elapsed:.1f}s")
    print(f"Avg processing:     {avg_processing:.0f}ms")

    print(f"\n{'='*60}")
    print("VERIFICATION STATUS BREAKDOWN")
    print(f"{'='*60}")

    for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
        pct = (count / len(valid_results)) * 100 if valid_results else 0
        bar = "█" * int(pct / 2)
        print(f"  {status:20s}: {count:3d} ({pct:5.1f}%) {bar}")

    # Score distribution
    scores = [r.get("authenticity_score", 0) for r in valid_results if "authenticity_score" in r]
    if scores:
        print(f"\n{'='*60}")
        print("AUTHENTICITY SCORE DISTRIBUTION")
        print(f"{'='*60}")

        score_ranges = {
            "0-20 (Low)": len([s for s in scores if 0 <= s <= 20]),
            "21-40 (Below Avg)": len([s for s in scores if 21 <= s <= 40]),
            "41-60 (Average)": len([s for s in scores if 41 <= s <= 60]),
            "61-80 (Above Avg)": len([s for s in scores if 61 <= s <= 80]),
            "81-100 (High)": len([s for s in scores if 81 <= s <= 100]),
        }

        for range_name, count in score_ranges.items():
            pct = (count / len(scores)) * 100 if scores else 0
            bar = "█" * int(pct / 2)
            print(f"  {range_name:20s}: {count:3d} ({pct:5.1f}%) {bar}")

        print(f"\n  Average score: {sum(scores)/len(scores):.1f}")
        print(f"  Min score:     {min(scores)}")
        print(f"  Max score:     {max(scores)}")

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Stress test authenticity API")
    parser.add_argument("--requests", type=int, default=100, help="Number of requests")
    parser.add_argument("--concurrent", type=int, default=5, help="Max concurrent requests")
    args = parser.parse_args()

    asyncio.run(run_stress_test(args.requests, args.concurrent))
