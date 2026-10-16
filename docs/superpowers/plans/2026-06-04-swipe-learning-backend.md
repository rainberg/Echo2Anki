# 抖音式学习滑动流 — 后端 API 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add swipe feed API endpoints and SegmentRating model to the existing anki-app backend, enabling the React Native APP to fetch adaptive-difficulty segment feeds.

**Architecture:** New `SegmentRating` model tracks user difficulty annotations. New `routers/swipe.py` provides feed/rate/collect/stats endpoints. The feed endpoint uses a simple adaptive algorithm: 80% segments at or below the user's current level, 20% above. Level adjusts when 5 consecutive same-direction ratings occur.

**Tech Stack:** FastAPI + SQLAlchemy async + asyncpg (PostgreSQL), pytest + pytest-asyncio + aiosqlite (testing)

---

### Task 1: Add SegmentRating model

**Files:**
- Modify: `backend/app/models.py` (append after HelpArticle class)
- Create: `backend/tests/test_swipe_model.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_swipe_model.py`:

```python
import pytest
from sqlalchemy import select
from app.models import SegmentRating


def test_segment_rating_create(db_session):
    """SegmentRating can be created and stored"""
    rating = SegmentRating(
        user_id=None,
        segment_id="00000000-0000-0000-0000-000000000001",
        rating="easy",
        is_collected=False,
    )
    db_session.add(rating)
    db_session.commit()

    result = db_session.execute(select(SegmentRating))
    found = result.scalar_one()
    assert found.rating == "easy"
    assert found.is_collected is False
    assert found.user_id is None
    assert found.id is not None
    assert found.created_at is not None


def test_segment_rating_unique_constraint(db_session):
    """Each user can only have one rating per segment"""
    from uuid import uuid4
    uid = uuid4()
    sid = uuid4()
    r1 = SegmentRating(user_id=uid, segment_id=sid, rating="easy")
    db_session.add(r1)
    db_session.commit()

    r2 = SegmentRating(user_id=uid, segment_id=sid, rating="hard")
    db_session.add(r2)
    with pytest.raises(Exception):
        db_session.commit()


def test_segment_rating_update(db_session):
    """Rating can be updated by upserting"""
    from uuid import uuid4
    uid = uuid4()
    sid = uuid4()
    r1 = SegmentRating(user_id=uid, segment_id=sid, rating="easy")
    db_session.add(r1)
    db_session.commit()

    # Update the rating
    r1.rating = "hard"
    r1.is_collected = True
    db_session.commit()

    result = db_session.execute(select(SegmentRating))
    found = result.scalar_one()
    assert found.rating == "hard"
    assert found.is_collected is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd d:\00_dev\anki-app\backend && python -m pytest tests/test_swipe_model.py -v`
Expected: FAIL with `ImportError: cannot import name 'SegmentRating'`

- [ ] **Step 3: Add SegmentRating model to models.py**

Append to `backend/app/models.py` after the HelpArticle class:

```python
class SegmentRating(Base):
    __tablename__ = "segment_ratings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    segment_id = Column(UUID(as_uuid=True), ForeignKey("segments.id", ondelete="CASCADE"), nullable=False, index=True)
    rating = Column(String(10), nullable=False)
    is_collected = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "segment_id"),)
```

- [ ] **Step 4: Add SegmentRating import to conftest.py**

In `backend/tests/conftest.py`, add `SegmentRating` to the import list from `app.models`.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd d:\00_dev\anki-app\backend && python -m pytest tests/test_swipe_model.py -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/models.py backend/tests/test_swipe_model.py backend/tests/conftest.py
git commit -m "feat: add SegmentRating model for swipe learning difficulty annotations"
```

---

### Task 2: Add swipe schemas

**Files:**
- Create: `backend/app/schemas_swipe.py`
- Create: `backend/tests/test_swipe_schemas.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_swipe_schemas.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd d:\00_dev\anki-app\backend && python -m pytest tests/test_swipe_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create schemas_swipe.py**

Create `backend/app/schemas_swipe.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd d:\00_dev\anki-app\backend && python -m pytest tests/test_swipe_schemas.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas_swipe.py backend/tests/test_swipe_schemas.py
git commit -m "feat: add swipe feed schemas for learning app API"
```

---

### Task 3: Add swipe router — feed endpoint

**Files:**
- Create: `backend/app/routers/swipe.py`
- Create: `backend/tests/test_swipe_router.py`

- [ ] **Step 1: Write the failing test for feed endpoint**

Create `backend/tests/test_swipe_router.py`:

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.database import get_db
from app.deps import get_admin_user, get_current_user, get_optional_user
from app.models import Segment, Task, PublicShare, SegmentRating, User


@pytest.fixture
def client(db_session):
    def _get_db_override():
        yield db_session

    app.dependency_overrides[get_db] = _get_db_override
    app.dependency_overrides[get_optional_user] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: type("User", (), {"id": "00000000-0000-0000-0000-000000000001", "role": "user"})()
    app.dependency_overrides[get_admin_user] = lambda: type("User", (), {"id": "00000000-0000-0000-0000-000000000001", "role": "admin"})()

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


def _seed_segments(db_session):
    """Create test segments with a public share"""
    # Create a user
    user = User(
        id="00000000-0000-0000-0000-000000000001",
        email="test@test.com",
        display_name="Test",
        role="user",
        credits=100,
    )
    db_session.add(user)

    # Create a task
    task = Task(
        id="00000000-0000-0000-0000-000000000010",
        user_id=user.id,
        file_name="test.mp3",
        file_hash="abc123",
        file_duration_sec=60.0,
        status="completed",
    )
    db_session.add(task)

    # Create a public share
    share = PublicShare(
        id="00000000-0000-0000-0000-000000000020",
        task_id=task.id,
        user_id=user.id,
        title="Test Share",
        difficulty="A2",
        category="daily",
    )
    db_session.add(share)

    # Create segments
    segments = []
    for i, (diff, de, zh) in enumerate([
        ("A1", "Guten Morgen.", "早上好。"),
        ("A1", "Wie geht es dir?", "你好吗？"),
        ("A2", "Ich möchte einen Kaffee.", "我想要一杯咖啡。"),
        ("A2", "Können Sie mir helfen?", "您能帮我吗？"),
        ("B1", "Ich habe gestern ein interessantes Buch gelesen.", "我昨天读了一本有趣的书。"),
        ("B1", "Wenn ich mehr Zeit hätte, würde ich reisen.", "如果我有更多时间，我会去旅行。"),
        ("B2", "Die Wirtschaftslage hat sich in den letzten Monaten verschlechtert.", "近几个月经济形势恶化了。"),
        ("C1", "Die philosophischen Implikationen dieser Theorie sind weitreichend.", "这个理论的哲学意义是深远的。"),
    ]):
        seg = Segment(
            id=f"00000000-0000-0000-0000-{i+1:012d}",
            task_id=task.id,
            seq_index=i,
            start_time=float(i * 5),
            end_time=float(i * 5 + 4),
            german_text=de,
            chinese_text=zh,
        )
        segments.append(seg)
        db_session.add(seg)

    db_session.commit()
    return segments


def test_feed_returns_segments(client, db_session):
    """Feed endpoint returns segments"""
    _seed_segments(db_session)
    resp = client.get("/api/swipe/feed", params={"source": "public", "limit": 5})
    assert resp.status_code == 200
    data = resp.json()
    assert "segments" in data
    assert "current_level" in data
    assert "total_rated" in data
    assert len(data["segments"]) <= 5


def test_feed_default_level(client, db_session):
    """Feed defaults to B1 level when no ratings exist"""
    _seed_segments(db_session)
    resp = client.get("/api/swipe/feed", params={"source": "public", "limit": 5})
    data = resp.json()
    assert data["current_level"] == "B1"


def test_feed_with_level_param(client, db_session):
    """Feed respects level parameter"""
    _seed_segments(db_session)
    resp = client.get("/api/swipe/feed", params={"source": "public", "limit": 5, "level": "A1"})
    data = resp.json()
    assert data["current_level"] == "A1"


def test_rate_segment(client, db_session):
    """Rate endpoint creates a rating"""
    segments = _seed_segments(db_session)
    seg_id = str(segments[0].id)
    resp = client.post("/api/swipe/rate", json={"segment_id": seg_id, "rating": "easy"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["rating"] == "easy"


def test_rate_updates_existing(client, db_session):
    """Rating the same segment again updates it"""
    segments = _seed_segments(db_session)
    seg_id = str(segments[0].id)
    client.post("/api/swipe/rate", json={"segment_id": seg_id, "rating": "easy"})
    resp = client.post("/api/swipe/rate", json={"segment_id": seg_id, "rating": "hard"})
    assert resp.status_code == 200
    assert resp.json()["rating"] == "hard"


def test_stats_no_ratings(client, db_session):
    """Stats endpoint returns defaults when no ratings exist"""
    _seed_segments(db_session)
    resp = client.get("/api/swipe/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["current_level"] == "B1"
    assert data["total_rated"] == 0


def test_stats_with_ratings(client, db_session):
    """Stats endpoint reflects existing ratings"""
    segments = _seed_segments(db_session)
    # Rate 3 segments as easy
    for seg in segments[:3]:
        client.post("/api/swipe/rate", json={"segment_id": str(seg.id), "rating": "easy"})
    resp = client.get("/api/swipe/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_rated"] == 3
    assert data["easy_count"] == 3
    assert data["hard_count"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd d:\00_dev\anki-app\backend && python -m pytest tests/test_swipe_router.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.routers.swipe'`

- [ ] **Step 3: Create swipe router**

Create `backend/app/routers/swipe.py`:

```python
import random
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user, get_optional_user
from app.models import PublicShare, Segment, SegmentRating, Task, User
from app.schemas_swipe import (
    DIFFICULTY_LEVELS,
    SwipeCollectRequest,
    SwipeFeedResponse,
    SwipeFeedSegment,
    SwipeRateRequest,
    SwipeStatsResponse,
)

router = APIRouter(prefix="/swipe", tags=["swipe"])


def _level_index(level: str) -> int:
    try:
        return DIFFICULTY_LEVELS.index(level)
    except ValueError:
        return 2  # Default to B1


def _level_from_index(idx: int) -> str:
    return DIFFICULTY_LEVELS[max(0, min(len(DIFFICULTY_LEVELS) - 1, idx))]


async def _get_user_level(db: AsyncSession, user_id: Optional[UUID]) -> str:
    """Determine the user's current difficulty level based on recent ratings."""
    if user_id is None:
        return "B1"

    # Get consecutive easy/hard counts from recent ratings
    result = await db.execute(
        select(SegmentRating)
        .where(SegmentRating.user_id == user_id)
        .order_by(SegmentRating.created_at.desc())
        .limit(10)
    )
    recent = result.scalars().all()

    if not recent:
        return "B1"

    # Count consecutive same-direction ratings from most recent
    consecutive_easy = 0
    consecutive_hard = 0
    for r in recent:
        if r.rating == "easy":
            consecutive_easy += 1
        else:
            break

    for r in recent:
        if r.rating == "hard":
            consecutive_hard += 1
        else:
            break

    # Start from B1, adjust based on consecutive ratings
    # Check if user has a pattern of 5+ consecutive same direction
    current_idx = 2  # B1

    # Look for the last level shift by checking all ratings
    all_result = await db.execute(
        select(SegmentRating)
        .where(SegmentRating.user_id == user_id)
        .order_by(SegmentRating.created_at.asc())
    )
    all_ratings = all_result.scalars().all()

    # Simple level tracking: start at B1, shift on 5 consecutive
    level_idx = 2  # B1
    streak = 0
    last_direction = None
    for r in all_ratings:
        direction = r.rating
        if direction == last_direction:
            streak += 1
        else:
            streak = 1
            last_direction = direction

        if streak >= 5:
            if direction == "easy":
                level_idx = min(level_idx + 1, len(DIFFICULTY_LEVELS) - 1)
            else:
                level_idx = max(level_idx - 1, 0)
            streak = 0

    return _level_from_index(level_idx)


@router.get("/feed", response_model=SwipeFeedResponse)
async def get_swipe_feed(
    source: str = "public",
    limit: int = 10,
    level: str = None,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a batch of segments for the swipe feed."""
    if source not in ("public", "mine"):
        raise HTTPException(status_code=400, detail="source must be 'public' or 'mine'")

    # Determine current level
    current_level = level or await _get_user_level(db, user.id if user else None)
    level_idx = _level_index(current_level)

    # Build segment pool based on source
    if source == "public":
        # Segments from public shares
        pool_query = (
            select(Segment, PublicShare.difficulty.label("share_difficulty"), PublicShare.title.label("share_title"))
            .join(Task, Segment.task_id == Task.id)
            .join(PublicShare, PublicShare.task_id == Task.id)
        )
    else:
        if user is None:
            raise HTTPException(status_code=401, detail="Login required for 'mine' source")
        pool_query = (
            select(Segment, Task.difficulty.label("share_difficulty"), Task.file_name.label("share_title"))
            .join(Task, Segment.task_id == Task.id)
            .where(Task.user_id == user.id, Task.status == "completed")
        )

    # Exclude already rated segments
    if user:
        rated_subquery = select(SegmentRating.segment_id).where(SegmentRating.user_id == user.id)
        pool_query = pool_query.where(Segment.id.not_in(rated_subquery))

    # Split into familiar (current level and below) and challenge (above)
    familiar_levels = DIFFICULTY_LEVELS[: level_idx + 1]
    challenge_levels = DIFFICULTY_LEVELS[level_idx + 1 :]

    # Fetch familiar segments (80%)
    familiar_count = int(limit * 0.8)
    familiar_query = pool_query.where(PublicShare.difficulty.in_(familiar_levels) if source == "public" else Task.difficulty.in_(familiar_levels))
    familiar_result = await db.execute(familiar_query)
    familiar_rows = familiar_result.all()
    random.shuffle(familiar_rows)
    familiar_picked = familiar_rows[:familiar_count]

    # Fetch challenge segments (20%)
    challenge_count = limit - familiar_count
    challenge_rows = []
    if challenge_levels:
        challenge_query = pool_query.where(PublicShare.difficulty.in_(challenge_levels) if source == "public" else Task.difficulty.in_(challenge_levels))
        challenge_result = await db.execute(challenge_query)
        challenge_rows = challenge_result.all()
        random.shuffle(challenge_rows)
    challenge_picked = challenge_rows[:challenge_count]

    # Combine and shuffle
    all_picked = familiar_picked + challenge_picked
    random.shuffle(all_picked)

    # Count total rated
    total_rated = 0
    if user:
        count_result = await db.execute(
            select(func.count()).select_from(SegmentRating).where(SegmentRating.user_id == user.id)
        )
        total_rated = count_result.scalar() or 0

    # Build response
    segments = []
    for row in all_picked:
        seg = row[0]
        share_diff = row[1]
        share_title = row[2] if len(row) > 2 else ""

        # Build audio URL
        audio_url = f"/api/segments/{seg.id}/clip" if seg.clip_path else ""

        segments.append(
            SwipeFeedSegment(
                id=seg.id,
                german_text=seg.german_text,
                chinese_text=seg.chinese_text or "",
                audio_url=audio_url,
                difficulty=share_diff,
                source_title=share_title or "",
                duration=float(seg.end_time - seg.start_time) if seg.end_time and seg.start_time else 0.0,
            )
        )

    return SwipeFeedResponse(segments=segments, current_level=current_level, total_rated=total_rated)


@router.post("/rate")
async def rate_segment(
    body: SwipeRateRequest,
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Rate a segment as easy or hard."""
    # Verify segment exists
    result = await db.execute(select(Segment).where(Segment.id == body.segment_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Segment not found")

    # Upsert rating
    user_id = user.id if user else None
    existing = await db.execute(
        select(SegmentRating).where(
            SegmentRating.user_id == user_id,
            SegmentRating.segment_id == body.segment_id,
        )
    )
    rating = existing.scalar_one_or_none()

    if rating:
        rating.rating = body.rating
    else:
        rating = SegmentRating(
            user_id=user_id,
            segment_id=body.segment_id,
            rating=body.rating,
        )
        db.add(rating)

    await db.commit()
    return {"rating": body.rating, "segment_id": str(body.segment_id)}


@router.post("/collect")
async def collect_segment(
    body: SwipeCollectRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Collect a segment to a collection."""
    # Verify segment exists
    result = await db.execute(select(Segment).where(Segment.id == body.segment_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Segment not found")

    # Upsert rating with is_collected
    existing = await db.execute(
        select(SegmentRating).where(
            SegmentRating.user_id == user.id,
            SegmentRating.segment_id == body.segment_id,
        )
    )
    rating = existing.scalar_one_or_none()

    if rating:
        rating.is_collected = True
    else:
        rating = SegmentRating(
            user_id=user.id,
            segment_id=body.segment_id,
            rating="easy",
            is_collected=True,
        )
        db.add(rating)

    await db.commit()
    return {"collected": True, "segment_id": str(body.segment_id)}


@router.get("/stats", response_model=SwipeStatsResponse)
async def get_swipe_stats(
    user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Get swipe learning statistics."""
    user_id = user.id if user else None

    if user_id is None:
        return SwipeStatsResponse(
            current_level="B1", total_rated=0, easy_count=0, hard_count=0,
            consecutive_easy=0, consecutive_hard=0,
        )

    # Total counts
    easy_result = await db.execute(
        select(func.count()).select_from(SegmentRating).where(
            SegmentRating.user_id == user_id, SegmentRating.rating == "easy"
        )
    )
    hard_result = await db.execute(
        select(func.count()).select_from(SegmentRating).where(
            SegmentRating.user_id == user_id, SegmentRating.rating == "hard"
        )
    )
    easy_count = easy_result.scalar() or 0
    hard_count = hard_result.scalar() or 0

    # Consecutive counts
    recent = await db.execute(
        select(SegmentRating)
        .where(SegmentRating.user_id == user_id)
        .order_by(SegmentRating.created_at.desc())
        .limit(20)
    )
    recent_ratings = recent.scalars().all()

    consecutive_easy = 0
    for r in recent_ratings:
        if r.rating == "easy":
            consecutive_easy += 1
        else:
            break

    consecutive_hard = 0
    for r in recent_ratings:
        if r.rating == "hard":
            consecutive_hard += 1
        else:
            break

    current_level = await _get_user_level(db, user_id)

    return SwipeStatsResponse(
        current_level=current_level,
        total_rated=easy_count + hard_count,
        easy_count=easy_count,
        hard_count=hard_count,
        consecutive_easy=consecutive_easy,
        consecutive_hard=consecutive_hard,
    )
```

- [ ] **Step 4: Register router in main.py**

In `backend/app/main.py`, add import:

```python
from app.routers.swipe import router as swipe_router
```

Add router registration after the help router:

```python
app.include_router(swipe_router, prefix="/api")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd d:\00_dev\anki-app\backend && python -m pytest tests/test_swipe_router.py -v`
Expected: All tests PASS

- [ ] **Step 6: Run all swipe-related tests**

Run: `cd d:\00_dev\anki-app\backend && python -m pytest tests/test_swipe_model.py tests/test_swipe_schemas.py tests/test_swipe_router.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/swipe.py backend/app/schemas_swipe.py backend/app/main.py backend/tests/test_swipe_router.py
git commit -m "feat: add swipe feed API with adaptive difficulty recommendation"
```

---

### Task 4: Deploy and verify

**Files:**
- None (deployment task)

- [ ] **Step 1: Upload backend files to server**

Upload modified/new files to anki.3mudi.com:
- `backend/app/models.py`
- `backend/app/routers/swipe.py`
- `backend/app/schemas_swipe.py`
- `backend/app/main.py`

- [ ] **Step 2: Restart backend service**

Run on server: `sudo systemctl restart anki-api.service`

- [ ] **Step 3: Verify API is accessible**

Run: `curl -s https://anki.3mudi.com/api/swipe/feed?source=public&limit=3`
Expected: JSON response with segments array and current_level
