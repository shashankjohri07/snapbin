import pytest
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APIClient

from pastes.models import Paste


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def sample_paste():
    return Paste.objects.create(
        short_code="smpl1234",
        title="Sample",
        content="print('hello')",
        language="python",
        highlighted_html="<pre>print('hello')</pre>",
    )


@pytest.mark.django_db
class TestCreatePaste:
    def test_create_paste_success(self, api_client):
        response = api_client.post(
            "/api/pastes/",
            {"content": "print('hello')", "language": "python"},
            format="json",
        )
        assert response.status_code == 201
        assert "short_code" in response.data
        assert response.data["language"] == "python"

    def test_create_paste_empty_content(self, api_client):
        response = api_client.post("/api/pastes/", {}, format="json")
        assert response.status_code == 400

    def test_create_paste_with_expiry(self, api_client):
        response = api_client.post(
            "/api/pastes/",
            {"content": "temp", "expires_in": 3600},
            format="json",
        )
        assert response.status_code == 201
        assert response.data["expires_at"] is not None


@pytest.mark.django_db
class TestRetrievePaste:
    def test_retrieve_paste_success(self, api_client, sample_paste):
        response = api_client.get(f"/api/pastes/{sample_paste.short_code}/")
        assert response.status_code == 200
        assert response.data["content"] == "print('hello')"

    def test_retrieve_expired_paste(self, api_client):
        Paste.objects.create(
            short_code="expd1234",
            content="expired",
            expires_at=timezone.now() - timedelta(hours=1),
        )
        response = api_client.get("/api/pastes/expd1234/")
        assert response.status_code == 404

    def test_retrieve_nonexistent_paste(self, api_client):
        response = api_client.get("/api/pastes/noexist1/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestDeletePaste:
    def test_delete_paste(self, api_client, sample_paste):
        response = api_client.delete(f"/api/pastes/{sample_paste.short_code}/delete/")
        assert response.status_code == 204
        response = api_client.get(f"/api/pastes/{sample_paste.short_code}/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestListPastes:
    def test_list_pastes_paginated(self, api_client):
        for i in range(25):
            Paste.objects.create(short_code=f"list{i:04d}", content=f"content {i}")
        response = api_client.get("/api/pastes/list/")
        assert response.status_code == 200
        assert len(response.data["results"]) == 20
        assert response.data["count"] == 25
