#!/usr/bin/env python3
"""
CLI script for batch authenticity checking of URLs from a file.

Usage:
    python batch_check.py urls.txt --output results.json --concurrent 3 --depth standard

The input file should contain one URL per line.
Lines starting with # are treated as comments.
Blank lines are ignored.
"""

import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path
from typing import List, Dict, Any

from dotenv import load_dotenv

# Load environment variables before importing other modules
load_dotenv()

from models.batch import parse_url_file
from services.browserbase import extract_article_content
from agents.authenticity import authenticity_agent


async def process_url(
    url: str,
    check_depth: str,
    semaphore: asyncio.Semaphore
) -> Dict[str, Any]:
    """
    Process a single URL: fetch content and run authenticity check.

    Args:
        url: The URL to process
        check_depth: Check depth (quick/standard/thorough)
        semaphore: Semaphore for concurrency control

    Returns:
        Dict with URL, status, and result or error
    """
    async with semaphore:
        result_entry = {
            "url": url,
            "status": "error",
            "result": None,
            "error": None
        }

        try:
            print(f"[BATCH] Processing: {url}")

            # Step 1: Extract article content via Browserbase
            article_content = await extract_article_content(url)

            if not article_content or not article_content.full_text:
                result_entry["error"] = "Failed to extract article content"
                print(f"[BATCH] Failed to extract content from: {url}")
                return result_entry

            # Step 2: Run authenticity check
            item_id = str(uuid.uuid4())
            auth_result = await authenticity_agent(
                item_id=item_id,
                url=url,
                text=article_content.full_text,
                check_depth=check_depth
            )

            # Convert result to dict for JSON serialization
            result_dict = auth_result.model_dump()
            # Convert datetime to ISO format string
            if result_dict.get("checked_at"):
                result_dict["checked_at"] = result_dict["checked_at"].isoformat()

            result_entry["status"] = "success"
            result_entry["result"] = result_dict
            result_entry["article_title"] = article_content.title
            result_entry["article_source"] = article_content.source_name

            print(f"[BATCH] Completed: {url} - Score: {auth_result.authenticity_score}")

        except Exception as e:
            result_entry["error"] = str(e)
            print(f"[BATCH] Error processing {url}: {e}")

        return result_entry


async def batch_process(
    urls: List[str],
    max_concurrent: int,
    check_depth: str
) -> Dict[str, Any]:
    """
    Process multiple URLs with concurrency control.

    Args:
        urls: List of URLs to process
        max_concurrent: Maximum concurrent requests
        check_depth: Check depth for authenticity agent

    Returns:
        Dict with results and summary statistics
    """
    start_time = time.time()
    semaphore = asyncio.Semaphore(max_concurrent)

    # Process all URLs concurrently (limited by semaphore)
    tasks = [
        process_url(url, check_depth, semaphore)
        for url in urls
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle any exceptions that weren't caught
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            processed_results.append({
                "url": urls[i],
                "status": "error",
                "result": None,
                "error": str(result)
            })
        else:
            processed_results.append(result)

    # Calculate summary statistics
    successful = [r for r in processed_results if r["status"] == "success"]
    failed = [r for r in processed_results if r["status"] == "error"]

    total_time = time.time() - start_time

    return {
        "summary": {
            "total_urls": len(urls),
            "successful": len(successful),
            "failed": len(failed),
            "total_processing_time_seconds": round(total_time, 2),
            "average_time_per_url_seconds": round(total_time / len(urls), 2) if urls else 0
        },
        "results": processed_results
    }


def main():
    parser = argparse.ArgumentParser(
        description="Batch authenticity check for URLs from a file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python batch_check.py urls.txt
  python batch_check.py urls.txt -o results.json
  python batch_check.py urls.txt -c 5 -d thorough

Input file format:
  # This is a comment
  https://example.com/article1
  https://example.com/article2

  # Blank lines are ignored
  https://another-site.com/news
"""
    )

    parser.add_argument(
        "input_file",
        type=str,
        help="Path to file containing URLs (one per line)"
    )

    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="Output JSON file (default: stdout)"
    )

    parser.add_argument(
        "-c", "--concurrent",
        type=int,
        default=3,
        help="Maximum concurrent checks (default: 3)"
    )

    parser.add_argument(
        "-d", "--depth",
        type=str,
        choices=["quick", "standard", "thorough"],
        default="standard",
        help="Check depth: quick, standard, or thorough (default: standard)"
    )

    args = parser.parse_args()

    # Read input file
    input_path = Path(args.input_file)
    if not input_path.exists():
        print(f"Error: Input file not found: {args.input_file}", file=sys.stderr)
        sys.exit(1)

    try:
        content = input_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Error reading input file: {e}", file=sys.stderr)
        sys.exit(1)

    # Parse URLs
    urls, parse_errors = parse_url_file(content)

    if parse_errors:
        print("Warning: Some lines could not be parsed:", file=sys.stderr)
        for error in parse_errors:
            print(f"  {error}", file=sys.stderr)
        print(file=sys.stderr)

    if not urls:
        print("Error: No valid URLs found in input file", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(urls)} valid URL(s) to process", file=sys.stderr)
    print(f"Concurrency: {args.concurrent}, Depth: {args.depth}", file=sys.stderr)
    print(file=sys.stderr)

    # Run batch processing
    results = asyncio.run(batch_process(
        urls=urls,
        max_concurrent=args.concurrent,
        check_depth=args.depth
    ))

    # Add parse errors to output
    if parse_errors:
        results["parse_errors"] = parse_errors

    # Output results
    output_json = json.dumps(results, indent=2, default=str)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(output_json, encoding="utf-8")
        print(f"\nResults written to: {args.output}", file=sys.stderr)
    else:
        print(output_json)

    # Print summary to stderr
    summary = results["summary"]
    print(f"\nSummary:", file=sys.stderr)
    print(f"  Total URLs: {summary['total_urls']}", file=sys.stderr)
    print(f"  Successful: {summary['successful']}", file=sys.stderr)
    print(f"  Failed: {summary['failed']}", file=sys.stderr)
    print(f"  Total time: {summary['total_processing_time_seconds']}s", file=sys.stderr)


if __name__ == "__main__":
    main()
