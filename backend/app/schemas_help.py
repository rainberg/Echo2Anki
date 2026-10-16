from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class HelpArticleCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$")
    title: str = Field(..., min_length=1, max_length=200)
    content: str = ""
    category: str = Field(..., pattern=r"^(tasks|collections|anki)$")
    sort_order: int = 0
    is_published: bool = False


class HelpArticleUpdate(BaseModel):
    slug: Optional[str] = Field(default=None, min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$")
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    content: Optional[str] = None
    category: Optional[str] = Field(default=None, pattern=r"^(tasks|collections|anki)$")
    sort_order: Optional[int] = None
    is_published: Optional[bool] = None


class HelpArticleResponse(BaseModel):
    id: UUID
    slug: str
    title: str
    content: str
    category: str
    sort_order: int
    is_published: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class HelpArticleSummary(BaseModel):
    slug: str
    title: str


class HelpCategoryResponse(BaseModel):
    category: str
    label: str
    articles: List[HelpArticleSummary]


class HelpArticlePublicResponse(BaseModel):
    slug: str
    title: str
    content: str
    category: str
    updated_at: datetime

    model_config = {"from_attributes": True}
