"""
Pydantic models for News Authenticity feature
"""

from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel


class ArticleContent(BaseModel):
    """Content extracted from an article URL"""
    url: str
    title: str
    author: Optional[str] = None
    publication_date: Optional[str] = None
    source_domain: str
    source_name: Optional[str] = None
    full_text: str
    excerpt: str  # First 500 chars


class CrossReferenceResult(BaseModel):
    """A cross-reference source found for verification"""
    source_url: str
    source_name: str
    title: str
    excerpt: str
    full_text: Optional[str] = None
    publication_date: Optional[str] = None
    relevance_score: float = 0.0  # How relevant to original article


class FactClaim(BaseModel):
    """A factual claim extracted from an article"""
    claim: str
    claim_type: str  # "date", "fact", "quote", "statistic", "event"
    confidence: float  # 0-1 confidence that this is a verifiable claim
    source_in_article: Optional[str] = None  # Who/what is cited


class ClaimVerification(BaseModel):
    """Verification result for a single claim"""
    claim: str
    status: str  # "corroborated", "disputed", "unverified", "partial"
    supporting_sources: List[str] = []
    contradicting_sources: List[str] = []
    notes: Optional[str] = None


class AuthenticityResult(BaseModel):
    """Complete authenticity analysis result"""
    item_id: str
    authenticity_score: int  # 0-100
    confidence: float  # 0-1 confidence in the assessment
    verification_status: str  # "verified", "partially_verified", "unverified", "disputed"
    sources_checked: int
    corroborating_count: int
    conflicting_count: int
    key_claims: List[FactClaim] = []
    claim_verifications: List[ClaimVerification] = []
    explanation: str
    checked_at: datetime
    processing_time_ms: int = 0


class AuthenticityCheckRequest(BaseModel):
    """Request to check authenticity of an article"""
    item_id: str
    url: str
    text: str  # Article text/title from page
    check_depth: str = "standard"  # "quick", "standard", "thorough"


class AuthenticityCheckResponse(BaseModel):
    """Response with authenticity analysis"""
    item_id: str
    authenticity_score: int
    confidence: float
    verification_status: str
    sources_checked: int
    corroborating_count: int
    conflicting_count: int
    explanation: str
    checked_at: datetime
    processing_time_ms: int


class BatchAuthenticityRequest(BaseModel):
    """Batch request for multiple items"""
    items: List[AuthenticityCheckRequest]
    max_concurrent: int = 3


class BatchAuthenticityResponse(BaseModel):
    """Batch response"""
    results: List[AuthenticityCheckResponse]
    total_processing_time_ms: int
