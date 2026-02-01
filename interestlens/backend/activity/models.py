"""Activity tracking models for InterestLens."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class ClickData(BaseModel):
    """Data for a click interaction."""
    timestamp: int
    url: str
    text: str = ""
    title: str = ""
    isArticleLink: bool = False
    position: Optional[Dict[str, int]] = None


class PageVisitData(BaseModel):
    """Data for a page visit."""
    url: str
    domain: str
    title: str = ""
    timeSpent: int = 0  # milliseconds
    scrollDepth: int = 0  # percentage 0-100
    isArticle: bool = False
    categories: List[str] = Field(default_factory=list)
    clickCount: int = 0


class Activity(BaseModel):
    """A single activity event."""
    type: str  # 'page_visit', 'click'
    timestamp: int
    data: Dict[str, Any]
    sourceUrl: str = ""
    sourceDomain: str = ""


class TrackActivityRequest(BaseModel):
    """Request to track activities."""
    activities: List[Activity]
    client_timestamp: int
    user_id: Optional[str] = None


class TrackActivityResponse(BaseModel):
    """Response from tracking activities."""
    status: str = "ok"
    activities_processed: int = 0
    categories_updated: List[str] = Field(default_factory=list)


class ActivityHistoryRequest(BaseModel):
    """Request for activity history."""
    user_id: Optional[str] = None
    limit: int = 100
    offset: int = 0
    type_filter: Optional[str] = None  # 'page_visit', 'click'
    domain_filter: Optional[str] = None


class DomainStats(BaseModel):
    """Statistics for a domain."""
    domain: str
    visit_count: int
    total_time_spent: int  # milliseconds
    categories: List[str] = Field(default_factory=list)
    last_visit: int


class CategoryStats(BaseModel):
    """Statistics for a category."""
    category: str
    visit_count: int
    total_time_spent: int
    domains: List[str] = Field(default_factory=list)


class ActivityHistoryResponse(BaseModel):
    """Response with activity history."""
    activities: List[Activity] = Field(default_factory=list)
    total_count: int = 0
    domain_stats: List[DomainStats] = Field(default_factory=list)
    category_stats: List[CategoryStats] = Field(default_factory=list)
    top_categories: List[str] = Field(default_factory=list)
