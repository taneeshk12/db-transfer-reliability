"""Tests for the API client: credential handling, rate limiting and status handling (no network)."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from src.collector.api_client import TimetablesClient
from src.config import ApiCredentials

CREDS = ApiCredentials(client_id="test-client-id", api_key="test-api-key")


def _client(monkeypatch: pytest.MonkeyPatch, status: int, min_interval_s: float = 0.0) -> TimetablesClient:
    client = TimetablesClient(CREDS, min_interval_s=min_interval_s)
    fake = SimpleNamespace(status_code=status, text="<timetable/>", encoding=None, raise_for_status=lambda: None)
    monkeypatch.setattr(client.session, "get", lambda url, timeout: fake)
    return client


def test_credentials_are_sent_as_headers_but_never_in_repr() -> None:
    client = TimetablesClient(CREDS)
    assert client.session.headers["DB-Client-Id"] == "test-client-id"
    assert client.session.headers["DB-Api-Key"] == "test-api-key"
    assert "test-api-key" not in repr(client)
    assert "test-api-key" not in repr(CREDS)


def test_plan_404_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _client(monkeypatch, 404).plan("8000105", "260908", "23") is None


def test_auth_error_raises_clear_message(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(PermissionError, match="DB_CLIENT_ID"):
        _client(monkeypatch, 401).fchg("8000105")


def test_rate_limiter_spaces_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, 200, min_interval_s=0.2)
    start = time.monotonic()
    for _ in range(3):
        client.fchg("8000105")
    # 3 calls -> at least 2 full intervals between them
    assert time.monotonic() - start >= 0.4
    assert client.n_calls == 3
