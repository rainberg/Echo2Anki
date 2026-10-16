from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


DIFFICULTY_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]


class SwipeRateRequest(BaseModel):
    segment_id: UUID
    rating: str = Field(..., pattern=r"^(easy|hard)$")


class SwipeCollectRequest(BaseModel):
    segment_id: UUID
    collection_id: UUID


class SwipeFeedSegment(BaseModel):
    id: UUID
    german_text: str
    chinese_text: str = ""
    audio_url: str
    difficulty: Optional[str] = None
    source_title: str = ""
    duration: float = 0.0


class SwipeFeedResponse(BaseModel):
    segments: List[SwipeFeedSegment]
    current_level: str
    total_rated: int


class SwipeStatsResponse(BaseModel):
    current_level: str
    total_rated: int
    easy_count: int
    hard_count: int
    consecutive_easy: int
    consecutive_hard: int
