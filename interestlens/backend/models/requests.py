"""Request models for the API"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class DOMOutline(BaseModel):
    title: str
    headings: List[str] = []
    main_text_excerpt: str = ""


class PageItem(BaseModel):
    id: str
    href: Optional[str] = None
    text: str
    snippet: str = ""
    bbox: List[int] = []  # [x, y, width, height]
    thumbnail_base64: Optional[str] = None


class AnalyzePageRequest(BaseModel):
    page_url: str
    dom_outline: DOMOutline
    items: List[PageItem]
    screenshot_base64: Optional[str] = None


class ItemData(BaseModel):
    text: str
    topics: List[str] = []
    embedding: Optional[List[float]] = None


class EventRequest(BaseModel):
    event: str  # "click", "dwell", "thumbs_up", "thumbs_down"
    item_id: str
    page_url: str
    timestamp: int
    item_data: ItemData
    duration_ms: Optional[int] = None


class TokenRequest(BaseModel):
    user_id: str
    email: Optional[str] = None
    name: Optional[str] = None
    picture: Optional[str] = None
