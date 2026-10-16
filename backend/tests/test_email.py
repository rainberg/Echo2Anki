import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone
from uuid import uuid4


class TestEmailVerificationCodeModel:
    """测试邮件验证码模型"""

    def test_create_email_code(self, db_session):
        from app.models import EmailVerificationCode
        from app.email_service import get_code_expiry
        code = EmailVerificationCode(
            email="test@example.com",
            code="123456",
            purpose="register",
            expires_at=get_code_expiry(),
        )
        db_session.add(code)
        db_session.commit()

        result = db_session.query(EmailVerificationCode).filter_by(email="test@example.com").first()
        assert result is not None
        assert result.code == "123456"
        assert result.purpose == "register"

    def test_email_code_default_expiry(self, db_session):
        from app.models import EmailVerificationCode
        from app.email_service import get_code_expiry
        code = EmailVerificationCode(
            email="test@example.com",
            code="654321",
            purpose="reset_password",
            expires_at=get_code_expiry(),
        )
        db_session.add(code)
        db_session.commit()

        result = db_session.query(EmailVerificationCode).filter_by(email="test@example.com").first()
        assert result is not None
        assert result.expires_at is not None
        # expires_at should be in the future
        from datetime import datetime, timezone
        expires_aware = result.expires_at.replace(tzinfo=timezone.utc) if result.expires_at.tzinfo is None else result.expires_at
        assert expires_aware > datetime.now(timezone.utc)

    def test_email_code_is_used_default(self, db_session):
        from app.models import EmailVerificationCode
        from app.email_service import get_code_expiry
        code = EmailVerificationCode(
            email="test@example.com",
            code="111111",
            purpose="register",
            expires_at=get_code_expiry(),
        )
        db_session.add(code)
        db_session.commit()

        result = db_session.query(EmailVerificationCode).filter_by(email="test@example.com").first()
        assert result.is_used is False


class TestSendEmailVerificationAPI:
    """测试发送邮件验证码 API"""

    @pytest.mark.asyncio
    async def test_send_email_code_success(self, async_client, override_get_async_db):
        with patch("app.routers.email.send_email_code") as mock_send:
            mock_send.return_value = True
            response = await async_client.post("/api/email/send-code", json={
                "email": "test@example.com",
                "purpose": "register",
            })
            assert response.status_code == 200
            assert response.json()["success"] is True

    @pytest.mark.asyncio
    async def test_send_email_code_invalid_email(self, async_client, override_get_async_db):
        response = await async_client.post("/api/email/send-code", json={
            "email": "invalid-email",
            "purpose": "register",
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_send_email_code_invalid_purpose(self, async_client, override_get_async_db):
        response = await async_client.post("/api/email/send-code", json={
            "email": "test@example.com",
            "purpose": "invalid_purpose",
        })
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_send_email_code_rate_limit(self, async_client, override_get_async_db):
        """60秒内不能重复发送"""
        with patch("app.routers.email.send_email_code") as mock_send:
            mock_send.return_value = True
            # First request should succeed
            response1 = await async_client.post("/api/email/send-code", json={
                "email": "test@example.com",
                "purpose": "register",
            })
            assert response1.status_code == 200

            # Second request within 60s should be rate limited
            response2 = await async_client.post("/api/email/send-code", json={
                "email": "test@example.com",
                "purpose": "register",
            })
            assert response2.status_code == 429


class TestVerifyEmailCodeAPI:
    """测试验证邮件验证码 API"""

    @pytest.mark.asyncio
    async def test_verify_email_code_success(self, async_client, override_get_async_db, db_session):
        with patch("app.routers.email.send_email_code") as mock_send:
            mock_send.return_value = True
            # First send the code
            send_resp = await async_client.post("/api/email/send-code", json={
                "email": "verify@example.com",
                "purpose": "register",
            })
            assert send_resp.status_code == 200

        # Get the code from the database using the sync session (same DB file)
        from app.models import EmailVerificationCode
        code_record = db_session.query(EmailVerificationCode).filter_by(
            email="verify@example.com", purpose="register"
        ).order_by(EmailVerificationCode.created_at.desc()).first()
        assert code_record is not None
        actual_code = code_record.code

        # Then verify with the actual code
        response = await async_client.post("/api/email/verify-code", json={
            "email": "verify@example.com",
            "code": actual_code,
            "purpose": "register",
        })
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_verify_email_code_wrong_code(self, async_client, override_get_async_db):
        response = await async_client.post("/api/email/verify-code", json={
            "email": "test@example.com",
            "code": "000000",
            "purpose": "register",
        })
        assert response.status_code == 400


class TestEmailService:
    """测试邮件发送服务"""

    def test_generate_verification_code(self):
        from app.email_service import generate_verification_code
        code = generate_verification_code()
        assert len(code) == 6
        assert code.isdigit()

    def test_generate_verification_code_is_random(self):
        from app.email_service import generate_verification_code
        codes = set(generate_verification_code() for _ in range(100))
        # Should generate different codes (extremely unlikely to get 100 identical)
        assert len(codes) > 90

    @patch("app.email_service.smtplib.SMTP_SSL")
    def test_send_email_code_via_smtp(self, mock_smtp_ssl):
        from app.email_service import send_email_code
        mock_instance = MagicMock()
        mock_smtp_ssl.return_value.__enter__.return_value = mock_instance

        result = send_email_code("test@example.com", "123456")

        assert result is True
        mock_instance.login.assert_called_once()
        mock_instance.sendmail.assert_called_once()

    @patch("app.email_service.smtplib.SMTP_SSL")
    def test_send_email_code_smtp_failure(self, mock_smtp_ssl):
        from app.email_service import send_email_code
        mock_smtp_ssl.return_value.__enter__.side_effect = Exception("SMTP error")

        result = send_email_code("test@example.com", "123456")

        assert result is False