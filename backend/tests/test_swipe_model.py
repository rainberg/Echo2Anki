import pytest
from uuid import uuid4
from sqlalchemy import select
from app.models import SegmentRating


def test_segment_rating_create(db_session):
    """SegmentRating can be created and stored"""
    rating = SegmentRating(
        user_id=None,
        segment_id=uuid4(),
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
    """Rating can be updated"""
    uid = uuid4()
    sid = uuid4()
    r1 = SegmentRating(user_id=uid, segment_id=sid, rating="easy")
    db_session.add(r1)
    db_session.commit()

    r1.rating = "hard"
    r1.is_collected = True
    db_session.commit()

    result = db_session.execute(select(SegmentRating))
    found = result.scalar_one()
    assert found.rating == "hard"
    assert found.is_collected is True
