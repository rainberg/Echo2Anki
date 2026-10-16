import pytest
from pydantic import ValidationError


def test_swipe_rate_valid():
    from app.schemas_swipe import SwipeRateRequest
    data = SwipeRateRequest(segment_id="00000000-0000-0000-0000-000000000001", rating="easy")
    assert data.rating == "easy"


def test_swipe_rate_invalid():
    from app.schemas_swipe import SwipeRateRequest
    with pytest.raises(ValidationError):
        SwipeRateRequest(segment_id="00000000-0000-0000-0000-000000000001", rating="medium")


def test_swipe_collect_valid():
    from app.schemas_swipe import SwipeCollectRequest
    data = SwipeCollectRequest(
        segment_id="00000000-0000-0000-0000-000000000001",
        collection_id="00000000-0000-0000-0000-000000000002",
    )
    assert data.collection_id is not None


def test_swipe_feed_segment():
    from app.schemas_swipe import SwipeFeedSegment
    data = SwipeFeedSegment(
        id="00000000-0000-0000-0000-000000000001",
        german_text="Ich möchte einen Kaffee.",
        chinese_text="我想要一杯咖啡。",
        audio_url="/api/segments/xxx/audio",
        difficulty="A2",
        source_title="日常对话 #3",
        duration=3.5,
    )
    assert data.difficulty == "A2"


def test_swipe_stats_response():
    from app.schemas_swipe import SwipeStatsResponse
    data = SwipeStatsResponse(
        current_level="B1",
        total_rated=42,
        easy_count=30,
        hard_count=12,
        consecutive_easy=3,
        consecutive_hard=0,
    )
    assert data.current_level == "B1"
