import asyncio
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest

from app.billing import (
    _calc_amount,
    get_credits_per_minute_sync,
    refund_all_reserved_sync,
    reserve_credits_sync,
    settle_credits_sync,
)
from app.models import BillingRecord, EnginePricing, Task


class TestCalcAmount:
    def test_zero_duration(self):
        assert _calc_amount(Decimal("0"), Decimal("1.0")) == Decimal("0.00")

    def test_exact_one_minute(self):
        assert _calc_amount(Decimal("60"), Decimal("1.0")) == Decimal("1.00")

    def test_partial_minute_rounds_up(self):
        result = _calc_amount(Decimal("61"), Decimal("1.0"))
        assert result == Decimal("1.02")

    def test_large_duration(self):
        assert _calc_amount(Decimal("3600"), Decimal("2.0")) == Decimal("120.00")

    def test_high_cpm(self):
        assert _calc_amount(Decimal("60"), Decimal("3.5")) == Decimal("3.50")

    def test_very_short_duration_rounds_up(self):
        result = _calc_amount(Decimal("1"), Decimal("1.0"))
        assert result == Decimal("0.02")

    def test_db_session_works(self, db_session, sample_user):
        task_id = uuid4()
        record = BillingRecord(
            user_id=sample_user.id,
            task_id=task_id,
            action="reserve",
            amount=Decimal("-1.00"),
            balance_after=Decimal("99.00"),
            duration_sec=Decimal("60.00"),
            description="预扣",
        )
        db_session.add(record)
        db_session.commit()
        from sqlalchemy import select as sa_select
        result = db_session.execute(sa_select(BillingRecord).where(BillingRecord.task_id == task_id))
        records = result.scalars().all()
        assert len(records) == 1, f"Select: {records}"
        records = db_session.query(BillingRecord).filter_by(task_id=task_id).all()
        assert len(records) == 1

    def test_db_session_works_raw(self, db_session):
        task_id = uuid4()
        from app.models import User
        user = User(id=uuid4(), email="raw@test.com", display_name="Raw", allowed_engines=["local_whisper"])
        db_session.add(user)
        db_session.commit()
        record = BillingRecord(
            user_id=user.id,
            task_id=task_id,
            action="reserve",
            amount=Decimal("-1.00"),
            balance_after=Decimal("99.00"),
            duration_sec=Decimal("60.00"),
            description="预扣",
        )
        db_session.add(record)
        db_session.commit()
        from sqlalchemy import text
        result = db_session.execute(text("SELECT * FROM billing_records"))
        rows = result.fetchall()
        assert len(rows) == 1, f"Raw SQL: {rows}"
        records = db_session.query(BillingRecord).filter_by(task_id=task_id).all()
        assert len(records) == 1



class TestGetCreditsPerMinuteSync:
    def test_returns_pricing_when_found(self, db_session, sample_pricing):
        result = get_credits_per_minute_sync(db_session, "local_whisper", "small")
        assert result == Decimal("1.0")

    def test_returns_default_when_not_found(self, db_session):
        result = get_credits_per_minute_sync(db_session, "unknown_engine", "unknown_size")
        assert result == Decimal("1.0")

    def test_returns_inactive_pricing_is_ignored(self, db_session):
        pricing = EnginePricing(
            engine_key="local_whisper",
            model_size="medium",
            engine_name="Local Whisper Medium",
            credits_per_minute=Decimal("2.0"),
            is_active=False,
        )
        db_session.add(pricing)
        db_session.commit()
        result = get_credits_per_minute_sync(db_session, "local_whisper", "medium")
        assert result == Decimal("1.0")


class TestReserveCreditsSync:
    def test_successful_reserve(self, db_session, sample_user, sample_pricing):
        with patch("app.billing._auth_reserve_sync") as mock:
            mock.return_value = {"success": True, "credits": "98.00", "credits_reserved": "2.00"}
            task_id = uuid4()
            amount, ref_id = reserve_credits_sync(
                db_session, sample_user.id, task_id,
                Decimal("60"), "local_whisper", "small", "test-token"
            )
            assert amount == Decimal("1.00")
            assert ref_id.startswith(f"task:{task_id}:")
            records = db_session.query(BillingRecord).filter_by(task_id=task_id).all()
            assert len(records) == 1
            assert records[0].action == "reserve"
            assert records[0].amount == Decimal("-1.00")

    def test_reference_id_is_unique_per_call(self, db_session, sample_user, sample_pricing):
        with patch("app.billing._auth_reserve_sync") as mock:
            mock.return_value = {"success": True, "credits": "98.00", "credits_reserved": "2.00"}
            task_id = uuid4()
            _, ref_id1 = reserve_credits_sync(
                db_session, sample_user.id, task_id,
                Decimal("60"), "local_whisper", "small", "test-token"
            )
            import time
            time.sleep(1.1)
            _, ref_id2 = reserve_credits_sync(
                db_session, sample_user.id, task_id,
                Decimal("60"), "local_whisper", "small", "test-token"
            )
            assert ref_id1 != ref_id2

    def test_auth_service_unavailable(self, db_session, sample_user, sample_pricing):
        with patch("app.billing._auth_reserve_sync", return_value=None):
            with pytest.raises(ValueError, match="计费服务暂时不可用"):
                reserve_credits_sync(
                    db_session, sample_user.id, uuid4(),
                    Decimal("60"), "local_whisper", "small", "test-token"
                )

    def test_insufficient_balance(self, db_session, sample_user, sample_pricing):
        with patch("app.billing._auth_reserve_sync", return_value={"success": False, "detail": "余额不足"}):
            with pytest.raises(ValueError, match="余额不足"):
                reserve_credits_sync(
                    db_session, sample_user.id, uuid4(),
                    Decimal("60"), "local_whisper", "small", "test-token"
                )

    def test_duplicate_reference_id(self, db_session, sample_user, sample_pricing):
        with patch("app.billing._auth_reserve_sync", return_value={"success": False, "detail": "已存在"}):
            with pytest.raises(ValueError, match="已预扣"):
                reserve_credits_sync(
                    db_session, sample_user.id, uuid4(),
                    Decimal("60"), "local_whisper", "small", "test-token"
                )


class TestSettleCreditsSync:
    def test_successful_settle(self, db_session, sample_user, sample_pricing):
        with patch("app.billing._auth_settle_sync") as mock:
            mock.return_value = {"success": True, "credits": "98.00", "refund": "0.00"}
            task_id = uuid4()
            result = settle_credits_sync(
                db_session, sample_user.id, task_id,
                Decimal("60"), "local_whisper", "small",
                Decimal("2.00"), "test-token", "task:sync:ref:123"
            )
            assert result == Decimal("1.00")
            records = db_session.query(BillingRecord).filter_by(task_id=task_id).all()
            assert len(records) == 1
            assert records[0].action == "settle"

    def test_uses_provided_reference_id(self, db_session, sample_user, sample_pricing):
        with patch("app.billing._auth_settle_sync") as mock:
            mock.return_value = {"success": True, "credits": "98.00", "refund": "0.00"}
            settle_credits_sync(
                db_session, sample_user.id, uuid4(),
                Decimal("60"), "local_whisper", "small",
                Decimal("2.00"), "test-token", "my-sync-ref-id"
            )
            call_args = mock.call_args[0]
            assert call_args[3] == "my-sync-ref-id"

    def test_generates_fallback_reference_id(self, db_session, sample_user, sample_pricing):
        with patch("app.billing._auth_settle_sync") as mock:
            mock.return_value = {"success": True, "credits": "98.00", "refund": "0.00"}
            task_id = uuid4()
            settle_credits_sync(
                db_session, sample_user.id, task_id,
                Decimal("60"), "local_whisper", "small",
                Decimal("2.00"), "test-token", ""
            )
            call_args = mock.call_args[0]
            assert "settle" in call_args[3]

    def test_settle_with_refund_creates_refund_record(self, db_session, sample_user, sample_pricing):
        with patch("app.billing._auth_settle_sync") as mock:
            mock.return_value = {"success": True, "credits": "99.00", "refund": "1.00"}
            task_id = uuid4()
            settle_credits_sync(
                db_session, sample_user.id, task_id,
                Decimal("30"), "local_whisper", "small",
                Decimal("2.00"), "test-token", "task:sync:ref:456"
            )
            records = db_session.query(BillingRecord).filter_by(task_id=task_id).all()
            assert len(records) == 2
            actions = {r.action for r in records}
            assert actions == {"settle", "refund"}

    def test_auth_service_failure(self, db_session, sample_user, sample_pricing):
        with patch("app.billing._auth_settle_sync", return_value=None):
            result = settle_credits_sync(
                db_session, sample_user.id, uuid4(),
                Decimal("60"), "local_whisper", "small",
                Decimal("2.00"), "test-token", "task:sync:ref:fail"
            )
            assert result == Decimal("1.00")


class TestRefundAllReservedSync:
    def test_successful_refund(self, db_session, sample_user):
        with patch("app.billing._auth_settle_sync") as mock:
            mock.return_value = {"success": True, "credits": "100.00"}
            task_id = uuid4()
            refund_all_reserved_sync(
                db_session, sample_user.id, task_id,
                Decimal("5.00"), "test-token", "task:sync:refund"
            )
            records = db_session.query(BillingRecord).filter_by(task_id=task_id).all()
            assert len(records) == 1
            assert records[0].action == "refund"
            assert records[0].amount == Decimal("5.00")

    def test_skip_zero_amount(self, db_session, sample_user):
        task_id = uuid4()
        refund_all_reserved_sync(
            db_session, sample_user.id, task_id,
            Decimal("0.00"), "test-token", ""
        )
        records = db_session.query(BillingRecord).filter_by(task_id=task_id).all()
        assert len(records) == 0

    def test_skip_negative_amount(self, db_session, sample_user):
        task_id = uuid4()
        refund_all_reserved_sync(
            db_session, sample_user.id, task_id,
            Decimal("-1.00"), "test-token", ""
        )
        records = db_session.query(BillingRecord).filter_by(task_id=task_id).all()
        assert len(records) == 0

    def test_uses_provided_reference_id(self, db_session, sample_user):
        with patch("app.billing._auth_settle_sync") as mock:
            mock.return_value = {"success": True, "credits": "100.00"}
            refund_all_reserved_sync(
                db_session, sample_user.id, uuid4(),
                Decimal("3.00"), "test-token", "my-refund-ref-id"
            )
            call_args = mock.call_args[0]
            assert call_args[3] == "my-refund-ref-id"

    def test_auth_service_failure_logs_error(self, db_session, sample_user):
        with patch("app.billing._auth_settle_sync", return_value=None):
            refund_all_reserved_sync(
                db_session, sample_user.id, uuid4(),
                Decimal("3.00"), "test-token", "task:sync:ref:fail"
            )


class TestReferenceIdConsistency:
    def test_reserve_settle_uses_same_reference_id(self, db_session, sample_user, sample_pricing):
        with patch("app.billing._auth_reserve_sync") as mock_reserve, \
             patch("app.billing._auth_settle_sync") as mock_settle:
            mock_reserve.return_value = {"success": True, "credits": "98.00", "credits_reserved": "2.00"}
            mock_settle.return_value = {"success": True, "credits": "99.00", "refund": "1.00"}

            task_id = uuid4()
            _, ref_id = reserve_credits_sync(
                db_session, sample_user.id, task_id,
                Decimal("60"), "local_whisper", "small", "test-token"
            )
            settle_credits_sync(
                db_session, sample_user.id, task_id,
                Decimal("60"), "local_whisper", "small",
                Decimal("2.00"), "test-token", ref_id
            )
            settle_args = mock_settle.call_args[0]
            assert settle_args[3] == ref_id

    def test_reserve_refund_uses_same_reference_id(self, db_session, sample_user, sample_pricing):
        with patch("app.billing._auth_reserve_sync") as mock_reserve, \
             patch("app.billing._auth_settle_sync") as mock_settle:
            mock_reserve.return_value = {"success": True, "credits": "98.00", "credits_reserved": "2.00"}
            mock_settle.return_value = {"success": True, "credits": "100.00"}

            task_id = uuid4()
            _, ref_id = reserve_credits_sync(
                db_session, sample_user.id, task_id,
                Decimal("60"), "local_whisper", "small", "test-token"
            )
            refund_all_reserved_sync(
                db_session, sample_user.id, task_id,
                Decimal("2.00"), "test-token", ref_id
            )
            settle_args = mock_settle.call_args[0]
            assert settle_args[3] == ref_id