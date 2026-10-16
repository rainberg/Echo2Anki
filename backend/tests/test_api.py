from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.models import Task, User


@pytest.mark.integration
class TestHealthAPI:
    async def test_health_check(self, async_client):
        response = await async_client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "2.0.0"


@pytest.mark.integration
class TestAuthMeAPI:
    async def test_get_me_authenticated(self, async_client, override_get_current_user, sample_user):
        response = await async_client.get("/api/auth/me")
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@example.com"
        assert data["role"] == "user"
        assert data["credits"] in (100.0, "100.00")

    async def test_get_me_unauthenticated(self, async_client, override_get_db):
        response = await async_client.get("/api/auth/me")
        assert response.status_code == 403


@pytest.mark.integration
class TestAdminAPI:
    async def test_list_users_as_admin(self, async_client, override_get_admin_user, sample_admin, sample_user):
        response = await async_client.get("/api/admin/users?page=1&per_page=20")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert len(data["items"]) >= 1

    async def test_list_users_as_regular_user(self, async_client, override_get_current_user, sample_user):
        response = await async_client.get("/api/admin/users?page=1&per_page=20")
        assert response.status_code == 403

    async def test_list_users_with_search(self, async_client, override_get_admin_user, sample_admin, sample_user):
        response = await async_client.get("/api/admin/users?page=1&per_page=20&search=test")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    async def test_list_users_with_search_no_match(self, async_client, override_get_admin_user, sample_admin, sample_user):
        response = await async_client.get("/api/admin/users?page=1&per_page=20&search=nonexistent_user_xyz")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

    async def test_update_user_engines(self, async_client, override_get_admin_user, sample_admin, sample_user, db_session):
        response = await async_client.put(
            f"/api/admin/users/{sample_user.id}/engines",
            json={"allowed_engines": ["local_whisper", "openai_whisper"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert "openai_whisper" in data["allowed_engines"]

    async def test_update_user_status(self, async_client, override_get_admin_user, sample_admin, sample_user):
        response = await async_client.put(
            f"/api/admin/users/{sample_user.id}/status",
            json={"is_active": False},
        )
        assert response.status_code == 200

    async def test_update_engines_as_regular_user(self, async_client, override_get_current_user, sample_user):
        response = await async_client.put(
            f"/api/admin/users/{sample_user.id}/engines",
            json={"allowed_engines": ["local_whisper"]},
        )
        assert response.status_code == 403

    async def test_topup_nonexistent_user(self, async_client, override_get_admin_user, sample_admin):
        fake_id = str(uuid4())
        response = await async_client.post(
            f"/api/admin/users/{fake_id}/topup",
            json={"amount": 100},
        )
        assert response.status_code == 404


@pytest.mark.integration
class TestTasksAPI:
    async def test_list_tasks(self, async_client, override_get_current_user, sample_user, sample_task):
        response = await async_client.get("/api/tasks")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert len(data["items"]) >= 1
        assert data["items"][0]["upload_name"] == "test.mp3"

    async def test_list_tasks_pagination(self, async_client, override_get_current_user, sample_user, sample_task):
        response = await async_client.get("/api/tasks?page=1&per_page=1")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["per_page"] == 1

    async def test_list_tasks_filter_by_stage(self, async_client, override_get_current_user, sample_user, sample_task):
        response = await async_client.get("/api/tasks?stage=done")
        assert response.status_code == 200
        data = response.json()
        for item in data["items"]:
            assert item["stage"] == "done"

    async def test_get_task_detail(self, async_client, override_get_current_user, sample_user, sample_task, sample_segments):
        response = await async_client.get(f"/api/tasks/{sample_task.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(sample_task.id)
        assert len(data["segments"]) == 3

    async def test_get_task_not_found(self, async_client, override_get_current_user, sample_user):
        fake_id = str(uuid4())
        response = await async_client.get(f"/api/tasks/{fake_id}")
        assert response.status_code == 404

    async def test_get_task_wrong_user(self, async_client, override_get_current_user, sample_user, sample_task):
        response = await async_client.get(f"/api/tasks/{sample_task.id}")
        assert response.status_code == 200

    async def test_update_task_is_public(self, async_client, override_get_current_user, sample_user, sample_task):
        response = await async_client.patch(
            f"/api/tasks/{sample_task.id}",
            json={"is_public": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_public"] is True

    async def test_update_task_not_found(self, async_client, override_get_current_user, sample_user):
        fake_id = str(uuid4())
        response = await async_client.patch(
            f"/api/tasks/{fake_id}",
            json={"is_public": True},
        )
        assert response.status_code == 404

    async def test_delete_task_not_running(self, async_client, override_get_current_user, sample_user, sample_task):
        response = await async_client.delete(f"/api/tasks/{sample_task.id}")
        assert response.status_code == 204

    async def test_delete_task_not_found(self, async_client, override_get_current_user, sample_user):
        fake_id = str(uuid4())
        response = await async_client.delete(f"/api/tasks/{fake_id}")
        assert response.status_code == 404

    async def test_retry_task_not_failed(self, async_client, override_get_current_user, sample_user, sample_task):
        response = await async_client.post(f"/api/tasks/{sample_task.id}/retry", json={})
        assert response.status_code == 400

    async def test_cancel_task_already_done(self, async_client, override_get_current_user, sample_user, sample_task):
        response = await async_client.post(f"/api/tasks/{sample_task.id}/cancel")
        assert response.status_code == 400

    async def test_list_tasks_unauthenticated(self, async_client, override_get_db):
        response = await async_client.get("/api/tasks")
        assert response.status_code == 403


@pytest.mark.integration
class TestCollectionsAPI:
    async def test_create_collection(self, async_client, override_get_current_user, sample_user):
        response = await async_client.post(
            "/api/collections",
            json={"name": "New Collection", "description": "Test"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Collection"
        assert data["item_count"] == 0

    async def test_create_collection_name_too_short(self, async_client, override_get_current_user, sample_user):
        response = await async_client.post(
            "/api/collections",
            json={"name": "", "description": "Test"},
        )
        assert response.status_code == 422

    async def test_create_collection_name_too_long(self, async_client, override_get_current_user, sample_user):
        response = await async_client.post(
            "/api/collections",
            json={"name": "A" * 201, "description": "Test"},
        )
        assert response.status_code == 422

    async def test_list_collections(self, async_client, override_get_current_user, sample_user, sample_collection):
        response = await async_client.get("/api/collections")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["name"] == "Test Collection"

    async def test_get_collection_detail(self, async_client, override_get_current_user, sample_user, sample_collection, sample_collection_item):
        response = await async_client.get(f"/api/collections/{sample_collection.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Test Collection"
        assert "items" in data

    async def test_get_collection_not_found(self, async_client, override_get_current_user, sample_user):
        fake_id = str(uuid4())
        response = await async_client.get(f"/api/collections/{fake_id}")
        assert response.status_code == 404

    async def test_update_collection(self, async_client, override_get_current_user, sample_user, sample_collection):
        response = await async_client.patch(
            f"/api/collections/{sample_collection.id}",
            json={"name": "Updated Name", "description": "Updated desc"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"

    async def test_update_collection_not_found(self, async_client, override_get_current_user, sample_user):
        fake_id = str(uuid4())
        response = await async_client.patch(
            f"/api/collections/{fake_id}",
            json={"name": "New Name"},
        )
        assert response.status_code == 404

    async def test_delete_collection(self, async_client, override_get_current_user, sample_user, sample_collection):
        response = await async_client.delete(f"/api/collections/{sample_collection.id}")
        assert response.status_code == 204

    async def test_delete_collection_not_found(self, async_client, override_get_current_user, sample_user):
        fake_id = str(uuid4())
        response = await async_client.delete(f"/api/collections/{fake_id}")
        assert response.status_code == 404

    async def test_add_items_to_collection(self, async_client, override_get_current_user, sample_user, sample_collection, sample_segments):
        response = await async_client.post(
            f"/api/collections/{sample_collection.id}/items",
            json={"segment_ids": [str(sample_segments[1].id)]},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    async def test_add_duplicate_items(self, async_client, override_get_current_user, sample_user, sample_collection, sample_collection_item, sample_segments):
        response = await async_client.post(
            f"/api/collections/{sample_collection.id}/items",
            json={"segment_ids": [str(sample_segments[0].id)]},
        )
        assert response.status_code == 200
        assert len(response.json()) == 0

    async def test_add_items_collection_not_found(self, async_client, override_get_current_user, sample_user, sample_segments):
        fake_id = str(uuid4())
        response = await async_client.post(
            f"/api/collections/{fake_id}/items",
            json={"segment_ids": [str(sample_segments[0].id)]},
        )
        assert response.status_code == 404

    async def test_remove_item(self, async_client, override_get_current_user, sample_user, sample_collection, sample_collection_item):
        response = await async_client.delete(
            f"/api/collections/{sample_collection.id}/items/{sample_collection_item.id}"
        )
        assert response.status_code == 204

    async def test_remove_item_not_found(self, async_client, override_get_current_user, sample_user, sample_collection):
        fake_id = str(uuid4())
        response = await async_client.delete(
            f"/api/collections/{sample_collection.id}/items/{fake_id}"
        )
        assert response.status_code == 404

    async def test_toggle_item_push(self, async_client, override_get_current_user, sample_user, sample_collection, sample_collection_item):
        response = await async_client.patch(
            f"/api/collections/{sample_collection.id}/items/{sample_collection_item.id}",
            json={"push_enabled": False},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["push_enabled"] is False

    async def test_list_collections_unauthenticated(self, async_client, override_get_db):
        response = await async_client.get("/api/collections")
        assert response.status_code == 403


@pytest.mark.integration
class TestBillingAPI:
    async def test_get_balance(self, async_client, override_get_current_user, sample_user, sample_billing_record):
        response = await async_client.get("/api/billing/balance")
        assert response.status_code == 200
        data = response.json()
        assert "credits" in data
        assert "total_used" in data
        assert "total_tasks" in data
        assert "total_duration_sec" in data

    async def test_get_balance_no_records(self, async_client, override_get_current_user, sample_user):
        response = await async_client.get("/api/billing/balance")
        assert response.status_code == 200
        data = response.json()
        assert data["total_tasks"] == 0

    async def test_get_records(self, async_client, override_get_current_user, sample_user, sample_billing_record):
        response = await async_client.get("/api/billing/records")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert len(data["items"]) >= 1
        assert data["items"][0]["action"] == "reserve"

    async def test_get_records_pagination(self, async_client, override_get_current_user, sample_user, sample_billing_record):
        response = await async_client.get("/api/billing/records?page=1&per_page=1")
        assert response.status_code == 200
        data = response.json()
        assert data["page"] == 1
        assert data["per_page"] == 1

    async def test_get_engines(self, async_client, override_get_current_user, sample_user, sample_pricing):
        response = await async_client.get("/api/billing/engines")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        engine_keys = [e["engine_key"] for e in data]
        assert "local_whisper" in engine_keys

    async def test_get_balance_unauthenticated(self, async_client, override_get_db):
        response = await async_client.get("/api/billing/balance")
        assert response.status_code == 403


@pytest.mark.integration
class TestSegmentsAPI:
    async def test_update_segment(self, async_client, override_get_current_user, sample_user, sample_task, sample_segments):
        seg_id = str(sample_segments[0].id)
        response = await async_client.patch(
            f"/api/segments/{seg_id}",
            json={"chinese_text": "新的翻译"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["chinese_text"] == "新的翻译"

    async def test_update_segment_not_found(self, async_client, override_get_current_user, sample_user):
        fake_id = str(uuid4())
        response = await async_client.patch(
            f"/api/segments/{fake_id}",
            json={"chinese_text": "test"},
        )
        assert response.status_code == 404

    async def test_update_segment_unauthenticated(self, async_client, override_get_db, sample_segments):
        seg_id = str(sample_segments[0].id)
        response = await async_client.patch(
            f"/api/segments/{seg_id}",
            json={"chinese_text": "test"},
        )
        assert response.status_code == 403


@pytest.mark.integration
class TestTagsAPI:
    async def test_create_tag(self, async_client, override_get_current_user, sample_user):
        response = await async_client.post(
            "/api/tags",
            json={"name": "new-tag", "color": "#00FF00"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "new-tag"
        assert data["color"] == "#00FF00"

    async def test_create_tag_default_color(self, async_client, override_get_current_user, sample_user):
        response = await async_client.post(
            "/api/tags",
            json={"name": "default-color-tag"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["color"] == "#4A90D9"

    async def test_create_tag_name_too_short(self, async_client, override_get_current_user, sample_user):
        response = await async_client.post(
            "/api/tags",
            json={"name": ""},
        )
        assert response.status_code == 422

    async def test_create_tag_name_too_long(self, async_client, override_get_current_user, sample_user):
        response = await async_client.post(
            "/api/tags",
            json={"name": "A" * 101},
        )
        assert response.status_code == 422

    async def test_list_tags(self, async_client, override_get_current_user, sample_user, sample_tag):
        response = await async_client.get("/api/tags")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["name"] == "test-tag"

    async def test_delete_tag(self, async_client, override_get_current_user, sample_user, sample_tag):
        response = await async_client.delete(f"/api/tags/{sample_tag.id}")
        assert response.status_code == 204

    async def test_delete_tag_not_found(self, async_client, override_get_current_user, sample_user):
        fake_id = str(uuid4())
        response = await async_client.delete(f"/api/tags/{fake_id}")
        assert response.status_code == 404

    async def test_list_tags_unauthenticated(self, async_client, override_get_db):
        response = await async_client.get("/api/tags")
        assert response.status_code == 403


@pytest.mark.integration
class TestSystemAPI:
    async def test_get_engines(self, async_client, override_get_current_user, sample_user, sample_pricing):
        response = await async_client.get("/api/system/engines")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_engines_unauthenticated(self, async_client, override_get_db):
        response = await async_client.get("/api/system/engines")
        assert response.status_code == 403


@pytest.mark.integration
class TestPublicAPI:
    async def test_list_public_tasks(self, async_client, override_get_async_db):
        response = await async_client.get("/api/public/tasks")
        assert response.status_code == 200

    async def test_get_public_task_not_found(self, async_client, override_get_async_db):
        fake_id = str(uuid4())
        response = await async_client.get(f"/api/public/tasks/{fake_id}")
        assert response.status_code == 404


@pytest.mark.integration
class TestAnkiAPI:
    async def test_get_configs(self, async_client, override_get_current_user, sample_user):
        response = await async_client.get("/api/anki/configs")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    async def test_get_configs_unauthenticated(self, async_client, override_get_db):
        response = await async_client.get("/api/anki/configs")
        assert response.status_code == 403


@pytest.mark.integration
class TestAPIErrorHandling:
    async def test_invalid_uuid_format(self, async_client, override_get_current_user, sample_user):
        response = await async_client.get("/api/tasks/not-a-uuid")
        assert response.status_code == 422

    async def test_invalid_per_page(self, async_client, override_get_current_user, sample_user):
        response = await async_client.get("/api/tasks?per_page=0")
        assert response.status_code == 200

    async def test_invalid_page(self, async_client, override_get_current_user, sample_user):
        response = await async_client.get("/api/tasks?page=0")
        assert response.status_code == 200

    async def test_missing_required_field(self, async_client, override_get_current_user, sample_user):
        response = await async_client.post("/api/collections", json={})
        assert response.status_code == 422