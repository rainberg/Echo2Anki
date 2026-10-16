from decimal import Decimal
from uuid import uuid4

from app.models import BillingRecord, User


class TestDatabaseSession:
    def test_insert_and_query(self, db_session):
        uid = uuid4()
        user = User(
            id=uid,
            email="debug@test.com",
            display_name="Debug",
            allowed_engines=["local_whisper"],
        )
        db_session.add(user)
        db_session.commit()

        from sqlalchemy import text
        result = db_session.execute(text("SELECT * FROM users"))
        rows = result.fetchall()
        assert len(rows) == 1

        record = BillingRecord(
            user_id=uid,
            task_id=uuid4(),
            action="reserve",
            amount=Decimal("-1.00"),
            balance_after=Decimal("99.00"),
            duration_sec=Decimal("60.00"),
            description="test",
        )
        db_session.add(record)
        db_session.commit()

        result = db_session.execute(text("SELECT * FROM billing_records"))
        rows = result.fetchall()
        assert len(rows) == 1