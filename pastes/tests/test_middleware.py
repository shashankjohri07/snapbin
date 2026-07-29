import pytest
from unittest.mock import patch, MagicMock

from django.test import RequestFactory

from pastes.middleware import RateLimitMiddleware


class TestRateLimitMiddleware:
    def setup_method(self):
        self.factory = RequestFactory()
        self.get_response = MagicMock(return_value=MagicMock(status_code=200))
        self.middleware = RateLimitMiddleware(self.get_response)

    @patch("pastes.middleware._redis", create=True)
    def test_under_limit(self, _):
        with patch("redis.from_url") as mock_redis:
            mock_conn = MagicMock()
            mock_conn.incr.return_value = 5
            mock_redis.return_value = mock_conn

            request = self.factory.get("/api/pastes/")
            response = self.middleware(request)
            assert response.status_code == 200

    @patch("pastes.middleware._redis", create=True)
    def test_at_limit(self, _):
        with patch("redis.from_url") as mock_redis:
            mock_conn = MagicMock()
            mock_conn.incr.return_value = 30
            mock_redis.return_value = mock_conn

            request = self.factory.get("/api/pastes/")
            response = self.middleware(request)
            assert response.status_code == 200

    @patch("pastes.middleware._redis", create=True)
    def test_over_limit(self, _):
        with patch("redis.from_url") as mock_redis:
            mock_conn = MagicMock()
            mock_conn.incr.return_value = 31
            mock_redis.return_value = mock_conn

            request = self.factory.get("/api/pastes/")
            response = self.middleware(request)
            assert response.status_code == 429

    def test_redis_down_fails_open(self):
        with patch("redis.from_url", side_effect=Exception("Connection refused")):
            request = self.factory.get("/api/pastes/")
            response = self.middleware(request)
            assert response.status_code == 200
