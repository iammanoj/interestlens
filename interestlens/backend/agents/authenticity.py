"""
News Authenticity Agent using Google Gemini
Extracts claims from articles and verifies them against cross-references
"""

import os
import json
import asyncio
from typing import List, Optional, Dict
from datetime import datetime
import time
import weave
import google.generativeai as genai

from models.authenticity import (
    ArticleContent,
    CrossReferenceResult,
    FactClaim,
    ClaimVerification,
    AuthenticityResult,
    AuthenticityCheckRequest
)
from services.browserbase import (
    extract_article_content,
    search_news_sources,
    fetch_cross_reference_content
)
from services.redis_client import (
    cache_authenticity_result,
    get_cached_authenticity
)

# Configure Gemini
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
fast_model = genai.GenerativeModel("gemini-2.0-flash-lite")

# Prompts
CLAIM_EXTRACTION_PROMPT = """You are a fact-checking assistant analyzing a news article.

Article Title: {title}
Article Text: {text}

Extract the key factual claims from this article. Focus on:
1. Specific dates, times, and numbers
2. Named individuals and their statements/quotes
3. Events and their descriptions
4. Statistics and data points
5. Attributed sources

For each claim, assess your confidence that it is a verifiable factual statement (vs opinion/speculation).

Return ONLY valid JSON (no markdown, no code blocks):
{{
  "article_type": "news|opinion|analysis|feature",
  "main_topic": "brief 5-10 word topic description",
  "claims": [
    {{
      "claim": "The specific factual claim",
      "claim_type": "date|fact|quote|statistic|event",
      "confidence": 0.0-1.0,
      "source_in_article": "Who/what is cited as source, if any, or null"
    }}
  ]
}}

Limit to top 8 most important/verifiable claims. If no verifiable claims found, return empty claims array."""


VERIFICATION_PROMPT = """You are a fact-checking assistant verifying news article claims against other sources.

Original Article Claims:
{claims_json}

Cross-Reference Sources Found:
{sources_json}

For each original claim, determine its verification status:
- CORROBORATED: The claim is confirmed by at least one other independent source
- DISPUTED: The claim is contradicted by a reliable source
- UNVERIFIED: The claim cannot be confirmed or denied by available sources
- PARTIAL: Some aspects are confirmed, others are unclear or missing

Calculate an overall authenticity score (0-100):
- 90-100: Most claims fully corroborated by multiple reliable sources
- 70-89: Majority of claims verified, minor details unconfirmed
- 50-69: Partially verified, some significant claims unconfirmed
- 30-49: Limited verification, several claims cannot be confirmed
- 0-29: Most claims disputed or completely unverifiable

Return ONLY valid JSON (no markdown, no code blocks):
{{
  "authenticity_score": 0-100,
  "verification_status": "verified|partially_verified|unverified|disputed",
  "claim_results": [
    {{
      "claim": "the original claim text",
      "status": "corroborated|disputed|unverified|partial",
      "supporting_sources": ["source names that support"],
      "contradicting_sources": ["source names that contradict"],
      "notes": "brief explanation"
    }}
  ],
  "explanation": "2-3 sentence summary explaining the verification results and any concerns",
  "confidence": 0.0-1.0
}}

If no cross-references were found, set verification_status to "unverified" and explain that no corroborating sources were available."""


async def extract_claims(title: str, text: str) -> tuple[str, str, List[FactClaim]]:
    """
    Extract factual claims from article text using Gemini.
    Returns: (article_type, main_topic, list of claims)
    """
    # Truncate text if too long
    truncated_text = text[:4000] if len(text) > 4000 else text

    prompt = CLAIM_EXTRACTION_PROMPT.format(
        title=title,
        text=truncated_text
    )

    print(f"[DEBUG] Extracting claims from: {title[:50]}...")

    try:
        response = await fast_model.generate_content_async(prompt)
        response_text = response.text.strip()
        print(f"[DEBUG] Gemini response: {response_text[:200]}...")

        # Clean up response (remove markdown code blocks if present)
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1])

        result = json.loads(response_text)

        claims = []
        for claim_data in result.get("claims", []):
            claims.append(FactClaim(
                claim=claim_data.get("claim", ""),
                claim_type=claim_data.get("claim_type", "fact"),
                confidence=float(claim_data.get("confidence", 0.5)),
                source_in_article=claim_data.get("source_in_article")
            ))

        print(f"[DEBUG] Extracted {len(claims)} claims")
        return (
            result.get("article_type", "news"),
            result.get("main_topic", ""),
            claims
        )

    except Exception as e:
        print(f"[ERROR] Error extracting claims: {e}")
        import traceback
        traceback.print_exc()
        return ("unknown", "", [])


@weave.op()
async def verify_claims(
    claims: List[FactClaim],
    cross_references: List[CrossReferenceResult]
) -> tuple[int, str, float, List[ClaimVerification], str]:
    """
    Verify claims against cross-reference sources using Gemini.
    Returns: (score, status, confidence, verifications, explanation)
    """
    if not claims:
        return (50, "unverified", 0.5, [], "No verifiable claims found in the article.")

    if not cross_references:
        return (
            40,
            "unverified",
            0.3,
            [ClaimVerification(
                claim=c.claim,
                status="unverified",
                notes="No cross-reference sources found"
            ) for c in claims],
            "Unable to verify: no corroborating sources found for this story."
        )

    # Prepare claims JSON
    claims_json = json.dumps([
        {
            "claim": c.claim,
            "type": c.claim_type,
            "source": c.source_in_article
        }
        for c in claims
    ], indent=2)

    # Prepare sources JSON (use excerpts to save tokens)
    sources_json = json.dumps([
        {
            "source": r.source_name,
            "title": r.title,
            "excerpt": r.excerpt[:500] if r.excerpt else "",
            "full_text": (r.full_text[:1000] if r.full_text else "")
        }
        for r in cross_references
    ], indent=2)

    prompt = VERIFICATION_PROMPT.format(
        claims_json=claims_json,
        sources_json=sources_json
    )

    try:
        response = await fast_model.generate_content_async(prompt)
        response_text = response.text.strip()

        # Clean up response
        if response_text.startswith("```"):
            lines = response_text.split("\n")
            response_text = "\n".join(lines[1:-1])

        result = json.loads(response_text)

        verifications = []
        for v in result.get("claim_results", []):
            verifications.append(ClaimVerification(
                claim=v.get("claim", ""),
                status=v.get("status", "unverified"),
                supporting_sources=v.get("supporting_sources", []),
                contradicting_sources=v.get("contradicting_sources", []),
                notes=v.get("notes")
            ))

        return (
            int(result.get("authenticity_score", 50)),
            result.get("verification_status", "unverified"),
            float(result.get("confidence", 0.5)),
            verifications,
            result.get("explanation", "")
        )

    except Exception as e:
        print(f"Error verifying claims: {e}")
        return (50, "unverified", 0.3, [], f"Verification error: {str(e)}")


@weave.op()
async def authenticity_agent(
    item_id: str,
    url: str,
    text: str,
    check_depth: str = "standard"
) -> AuthenticityResult:
    """
    Main authenticity agent that orchestrates the full verification pipeline.

    Steps:
    1. Check cache for existing result
    2. Extract full article content via Browserbase
    3. Extract claims using Gemini
    4. Search for cross-reference sources
    5. Fetch cross-reference content
    6. Verify claims against sources
    7. Cache and return result
    """
    start_time = time.time()

    # Check cache first
    cached = await get_cached_authenticity(item_id)
    if cached:
        return AuthenticityResult(**cached)

    # Default result for errors
    default_result = AuthenticityResult(
        item_id=item_id,
        authenticity_score=50,
        confidence=0.3,
        verification_status="unverified",
        sources_checked=0,
        corroborating_count=0,
        conflicting_count=0,
        key_claims=[],
        claim_verifications=[],
        explanation="Unable to perform authenticity check.",
        checked_at=datetime.utcnow(),
        processing_time_ms=0
    )

    try:
        # Step 1: Extract article content
        print(f"[DEBUG] Starting authenticity check for: {url}")
        article_content = await extract_article_content(url)
        print(f"[DEBUG] Browserbase result: {article_content is not None}")

        # Use provided text if extraction failed
        article_text = article_content.full_text if article_content else text
        article_title = article_content.title if article_content else ""
        print(f"[DEBUG] Article text length: {len(article_text)}, title: {article_title[:50] if article_title else 'None'}")

        if not article_text or len(article_text) < 100:
            article_text = text  # Fallback to provided text
            print(f"[DEBUG] Using fallback text: {text[:100]}...")

        # Step 2: Extract claims
        print(f"[DEBUG] Calling extract_claims...")
        article_type, main_topic, claims = await extract_claims(
            title=article_title or text[:100],
            text=article_text
        )
        print(f"[DEBUG] Claims extracted: {len(claims)}, type: {article_type}, topic: {main_topic}")

        if not claims:
            result = AuthenticityResult(
                item_id=item_id,
                authenticity_score=50,
                confidence=0.4,
                verification_status="unverified",
                sources_checked=0,
                corroborating_count=0,
                conflicting_count=0,
                key_claims=[],
                claim_verifications=[],
                explanation=f"No verifiable factual claims found. Article appears to be {article_type}.",
                checked_at=datetime.utcnow(),
                processing_time_ms=int((time.time() - start_time) * 1000)
            )
            await cache_authenticity_result(item_id, result.model_dump())
            return result

        # Step 3: Search for cross-references
        search_topic = main_topic or article_title or text[:100]
        exclude_domain = article_content.source_domain if article_content else ""

        cross_refs = await search_news_sources(
            topic=search_topic,
            exclude_domain=exclude_domain,
            max_results=5 if check_depth == "standard" else 3
        )

        # Step 4: Fetch cross-reference content (for thorough checks)
        if check_depth == "thorough" and cross_refs:
            cross_refs = await fetch_cross_reference_content(cross_refs, max_concurrent=3)

        # Step 5: Verify claims
        score, status, confidence, verifications, explanation = await verify_claims(
            claims=claims,
            cross_references=cross_refs
        )

        # Count corroborating/conflicting
        corroborating = sum(1 for v in verifications if v.status == "corroborated")
        conflicting = sum(1 for v in verifications if v.status == "disputed")

        result = AuthenticityResult(
            item_id=item_id,
            authenticity_score=score,
            confidence=confidence,
            verification_status=status,
            sources_checked=len(cross_refs),
            corroborating_count=corroborating,
            conflicting_count=conflicting,
            key_claims=claims,
            claim_verifications=verifications,
            explanation=explanation,
            checked_at=datetime.utcnow(),
            processing_time_ms=int((time.time() - start_time) * 1000)
        )

        # Cache result
        await cache_authenticity_result(item_id, result.model_dump())

        return result

    except Exception as e:
        print(f"Authenticity agent error: {e}")
        default_result.explanation = f"Error during authenticity check: {str(e)}"
        default_result.processing_time_ms = int((time.time() - start_time) * 1000)
        return default_result


@weave.op()
async def run_authenticity_checks(
    items: List[Dict],
    max_concurrent: int = 3
) -> Dict[str, AuthenticityResult]:
    """
    Run authenticity checks on multiple items with concurrency control.
    Returns dict mapping item_id to AuthenticityResult.
    """
    if not items:
        return {}

    semaphore = asyncio.Semaphore(max_concurrent)

    async def check_one(item: Dict) -> tuple[str, AuthenticityResult]:
        async with semaphore:
            result = await authenticity_agent(
                item_id=item.get("id", ""),
                url=item.get("href", item.get("url", "")),
                text=item.get("text", ""),
                check_depth="standard"
            )
            return (item.get("id", ""), result)

    results = await asyncio.gather(
        *[check_one(item) for item in items],
        return_exceptions=True
    )

    # Filter out exceptions and build dict
    return {
        item_id: result
        for item_id, result in results
        if isinstance(result, AuthenticityResult)
    }


def is_likely_news_article(item: Dict) -> bool:
    """
    Heuristic to determine if an item is likely a news article worth checking.
    """
    news_topics = {
        "news", "politics", "business", "finance", "tech", "technology",
        "science", "health", "world", "breaking", "report", "AI/ML",
        "cybersecurity", "climate", "research"
    }

    topics = item.get("topics", [])
    text = item.get("text", "").lower()

    # Check if any topic matches news categories
    if any(t.lower() in news_topics for t in topics):
        return True

    # Check text for news-like keywords
    news_keywords = ["announced", "reported", "according to", "study", "research", "says", "said"]
    if any(kw in text for kw in news_keywords):
        return True

    return False
