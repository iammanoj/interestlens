"""Response models for the API"""

from typing import List, Optional, Dict, Tuple
from pydantic import BaseModel


class ScoredItem(BaseModel):
    id: str
    score: int
    topics: List[str]
    why: str
    # Authenticity fields (optional, populated when authenticity check is performed)
    authenticity_score: Optional[int] = None
    authenticity_status: Optional[str] = None  # "verified", "partially_verified", "unverified", "disputed"
    authenticity_explanation: Optional[str] = None


class ProfileSummary(BaseModel):
    top_topics: List[Tuple[str, float]]


class AnalyzePageResponse(BaseModel):
    items: List[ScoredItem]
    page_topics: List[str] = []
    profile_summary: Optional[ProfileSummary] = None
    weave_trace_url: Optional[str] = None


class EventResponse(BaseModel):
    status: str
    profile_updated: bool
    new_top_topics: Optional[List[Tuple[str, float]]] = None
