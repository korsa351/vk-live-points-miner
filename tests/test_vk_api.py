import json
from unittest.mock import Mock

import pytest
from requests import HTTPError, Response

from VKLivePointsMiner.classes.VKApi import VKApi


@pytest.fixture
def api(monkeypatch):
    api = VKApi(Mock())
    monkeypatch.setattr(api, "_headers", lambda slug=None: {})
    return api


def reply(api, payload, *, status=200):
    response = Response()
    response.status_code = status
    response.url = "https://example.invalid"
    response._content = json.dumps(payload).encode()
    api._request = Mock(return_value=response)


def test_v8_stream_status_uses_nested_stream_and_viewer_count(api):
    stream = {"id": "stream-id", "status": "online", "title": "Live", "counters": {"viewers": 451}}
    reply(api, {"data": {"stream": stream}, "refs": {}})
    assert api.check_stream_status("channel") == {
        "stream_id": "stream-id", "title": "Live", "viewers": 451,
    }

    reply(api, {"data": {"stream": {**stream, "status": "offline"}}, "refs": {}})
    assert api.check_stream_status("channel") is None

    reply(api, {"data": {"stream": None}, "refs": {}})
    assert api.check_stream_status("channel") is None

    reply(api, {"isOnline": True, "streamId": "legacy", "viewers": 15})
    assert api.check_stream_status("channel")["stream_id"] == "legacy"


def test_v8_actor_channel_and_socket_are_unwrapped(api):
    actor = {"id": 17, "webSocketChannels": {"user_private": {"name": "users#private-id"}}}
    reply(api, {"data": {"actor": actor}})
    assert api.get_user_info() == actor
    assert api.user_id == 17
    assert api.user_channel == "users#private-id"

    reply(api, {"data": {"channel": {"id": 23}}, "refs": {}})
    assert api.get_channel_info("channel")["id"] == 23

    reply(api, {"data": {"webSocketConnection": {"token": "test-token"}}})
    assert api.get_ws_token() == "test-token"


def test_bonus_list_balance_and_claim_failure(api):
    reply(api, {"data": {"bonuses": [{"id": "pending-id", "bonus": {"amount": 100}}]}})
    assert api.get_pending_bonus("channel") == "pending-id"

    reply(api, {"data": {"bonuses": []}})
    assert api.get_pending_bonus("channel") is None

    reply(api, {"data": {"channelPoint": {"balance": 150}}})
    assert api.get_points_balance("channel") == 150

    reply(api, None, status=204)
    assert api.claim_bonus("channel", "pending-id")

    reply(api, {"error": "forbidden"}, status=403)
    with pytest.raises(HTTPError, match="403"):
        api.claim_bonus("channel", "pending-id")


def test_heartbeat_logs_http_status_when_rejected(api, caplog):
    reply(api, {"error": "forbidden"}, status=403)
    assert not api.send_heartbeat("channel", "stream-id")
    assert "Heartbeat failed for channel (HTTP 403)" in caplog.text
