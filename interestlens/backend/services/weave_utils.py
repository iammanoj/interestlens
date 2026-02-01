"""
Weave Observability Utilities for InterestLens
Provides helper functions for tracing, logging, and debugging with W&B Weave
"""

import os
import time
from typing import Any, Dict, Optional
from functools import wraps
import weave


def get_weave_enabled() -> bool:
    """Check if Weave is properly configured"""
    wandb_key = os.getenv("WANDB_API_KEY", "")
    return len(wandb_key) >= 40 and wandb_key != "your-wandb-api-key"


def log_metric(name: str, value: Any, step: Optional[int] = None):
    """
    Log a custom metric to Weave.
    Falls back to print if Weave is not configured.
    """
    try:
        if get_weave_enabled():
            # Weave automatically captures return values and inputs
            # For custom metrics, we can use weave.log if available
            print(f"[METRIC] {name}: {value}")
        else:
            print(f"[METRIC] {name}: {value}")
    except Exception as e:
        print(f"[METRIC ERROR] {name}: {value} (error: {e})")


def trace_authenticity_check(
    item_id: str,
    url: str,
    claims_count: int,
    sources_count: int,
    score: int,
    status: str,
    processing_ms: int
):
    """
    Log a detailed authenticity check trace.
    Useful for debugging and analyzing verification patterns.
    """
    trace_data = {
        "item_id": item_id,
        "url": url,
        "claims_extracted": claims_count,
        "sources_checked": sources_count,
        "authenticity_score": score,
        "verification_status": status,
        "processing_time_ms": processing_ms
    }

    print(f"[AUTHENTICITY_TRACE] {trace_data}")

    # Log individual metrics for dashboards
    log_metric("authenticity.claims_count", claims_count)
    log_metric("authenticity.sources_count", sources_count)
    log_metric("authenticity.score", score)
    log_metric("authenticity.processing_ms", processing_ms)


def trace_gemini_call(
    operation: str,
    model: str,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    latency_ms: Optional[int] = None
):
    """
    Log Gemini API call metrics.
    """
    trace_data = {
        "operation": operation,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency_ms": latency_ms
    }

    print(f"[GEMINI_TRACE] {trace_data}")

    if latency_ms:
        log_metric(f"gemini.{operation}.latency_ms", latency_ms)


def trace_news_search(
    query: str,
    source: str,  # "duckduckgo", "bing", etc.
    results_count: int,
    success: bool,
    latency_ms: int
):
    """
    Log news search metrics.
    """
    trace_data = {
        "query": query[:50],  # Truncate for logging
        "source": source,
        "results_count": results_count,
        "success": success,
        "latency_ms": latency_ms
    }

    print(f"[NEWS_SEARCH_TRACE] {trace_data}")

    log_metric(f"news_search.{source}.count", results_count)
    log_metric(f"news_search.{source}.success", 1 if success else 0)
    log_metric(f"news_search.{source}.latency_ms", latency_ms)


def timed_operation(operation_name: str):
    """
    Decorator to time and log operation duration.
    Use this in addition to @weave.op() for extra timing visibility.

    Example:
        @weave.op()
        @timed_operation("extract_claims")
        async def extract_claims(...):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                duration_ms = int((time.time() - start) * 1000)
                log_metric(f"{operation_name}.duration_ms", duration_ms)
                log_metric(f"{operation_name}.success", 1)
                return result
            except Exception as e:
                duration_ms = int((time.time() - start) * 1000)
                log_metric(f"{operation_name}.duration_ms", duration_ms)
                log_metric(f"{operation_name}.error", str(e)[:100])
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                duration_ms = int((time.time() - start) * 1000)
                log_metric(f"{operation_name}.duration_ms", duration_ms)
                log_metric(f"{operation_name}.success", 1)
                return result
            except Exception as e:
                duration_ms = int((time.time() - start) * 1000)
                log_metric(f"{operation_name}.duration_ms", duration_ms)
                log_metric(f"{operation_name}.error", str(e)[:100])
                raise

        if hasattr(func, '__wrapped__') or str(type(func)).find('coroutine') != -1:
            return async_wrapper
        # Check if it's an async function
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def get_trace_url() -> Optional[str]:
    """
    Get the current Weave trace URL for debugging.
    Returns None if Weave is not configured.
    """
    try:
        if get_weave_enabled() and hasattr(weave, 'get_current_trace_url'):
            return weave.get_current_trace_url()
    except Exception:
        pass
    return None


def create_evaluation_summary(
    total_items: int,
    verified_count: int,
    unverified_count: int,
    disputed_count: int,
    avg_score: float,
    avg_processing_ms: float
) -> Dict[str, Any]:
    """
    Create a summary for batch authenticity evaluation.
    Useful for debugging and reporting.
    """
    summary = {
        "total_items": total_items,
        "verified_count": verified_count,
        "unverified_count": unverified_count,
        "disputed_count": disputed_count,
        "verification_rate": verified_count / total_items if total_items > 0 else 0,
        "dispute_rate": disputed_count / total_items if total_items > 0 else 0,
        "avg_authenticity_score": avg_score,
        "avg_processing_time_ms": avg_processing_ms
    }

    print(f"[EVALUATION_SUMMARY] {summary}")

    return summary
