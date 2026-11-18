import json
from threading import Event, Thread
from unittest.mock import Mock
from urllib.parse import quote

import requests

from VKLivePointsMiner.VKLiveMiner import VKLiveMiner
from VKLivePointsMiner.VKWebServer import VKWebServer
from VKLivePointsMiner.classes.VKApi import VKApi
from VKLivePointsMiner.classes.VKAuth import VKAuth
from VKLivePointsMiner.classes.VKWebSocket import VKWebSocket
from VKLivePointsMiner.constants import DEFAULT_USER_AGENT


SESSION = {
    "access_token": "test-access", "refresh_token": "test-refresh",
    "expires_at": 1826478013072, "client_id": "test-client",
}


def test_dashboard_exposes_only_statistics(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    miner = VKLiveMiner({"streamers": [{"slug": "channel", "priority": 1}]})
    miner.auth.save_session(SESSION)
    miner.api.user_id = 123
    streamer = miner.streamers[0]
    streamer.is_online = True
    streamer.title = "Unpublished title"
    streamer.viewers = 25
    streamer.points = 500
    streamer.watch_time = 120
    miner.active_slots[streamer] = "internal-stream-id"
    client = VKWebServer(miner).app.test_client()

    assert "Статистика каналов" in client.get("/").text
    assert client.get("/static/dashboard.js").status_code == 200
    response = client.get("/api/status", base_url="http://public.example:8080")
    assert response.json == {
        "total_streamers": 1, "online_count": 1, "active_count": 1,
        "streamers": [{
            "slug": "channel", "is_online": True, "is_active": True,
            "viewers": 25, "points": 500, "watch_time": 120,
        }],
    }
    assert response.cache_control.no_store

    for path in ("/log", "/api/streamers", "/cookies/session.json",
                 "/config/config.json", "/static/../../cookies/session.json"):
        assert client.get(path).status_code == 404
    assert client.post("/api/auth/browser").status_code == 404
    assert client.post("/api/streamers", json={"slug": "new"}).status_code == 404
    assert client.delete("/api/streamers/channel").status_code == 404
    assert client.post("/api/status").status_code == 405


def test_private_session_file_accepts_fields_without_an_internal_valid_flag(tmp_path):
    auth = VKAuth(tmp_path)
    assert not auth.is_authorized()
    auth.save_session(SESSION)
    assert auth.is_authorized()
    assert auth.load_session() == {**SESSION, "user_agent": DEFAULT_USER_AGENT}

    auth.save_session({**SESSION, "valid": False})
    assert not auth.is_authorized()
    auth.save_session({**SESSION, "expires_at": 0})
    assert not auth.is_authorized()


def test_refresh_updates_the_mounted_session_file(tmp_path, monkeypatch):
    auth = VKAuth(tmp_path)
    auth.save_session(SESSION)
    new_cookie = {
        "accessToken": "replacement-access", "refreshToken": "replacement-refresh",
        "expiresAt": 1826478013073,
    }
    response = Mock(history=[], cookies={"auth": quote(json.dumps(new_cookie))})
    request = Mock(return_value=response)
    monkeypatch.setattr(requests, "get", request)

    assert auth.refresh_token_if_needed(force=True)
    assert request.call_args.kwargs["cookies"]["_clientId"] == SESSION["client_id"]
    assert auth.load_session() == {
        **SESSION, "user_agent": DEFAULT_USER_AGENT, "access_token": "replacement-access",
        "refresh_token": "replacement-refresh", "expires_at": 1826478013073,
    }

    response.cookies["auth"] = quote(json.dumps({**new_cookie, "accessToken": ""}))
    assert not auth.refresh_token_if_needed(force=True)
    assert auth.load_session()["access_token"] == "replacement-access"


def test_slot_switch_stops_previous_stream_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    miner = VKLiveMiner({
        "settings": {"max_active_slots": 1},
        "streamers": [{"slug": "backup", "priority": 2}, {"slug": "first", "priority": 1}],
    })
    miner.api = Mock()
    backup, first = miner.streamers
    for streamer in (backup, first):
        streamer.is_online = True
        streamer.stream_id = streamer.username + "-old"

    miner._update_active_slots()
    assert [item["slug"] for item in miner.statistics()["streamers"] if item["is_active"]] == ["first"]
    first.stream_id = "first-new"
    assert miner._update_active_slots() == {first}
    miner.api.stop_heartbeat.assert_called_once_with("first", "first-old")

    first.is_online = False
    first.stream_id = None
    miner._update_active_slots()
    miner.api.stop_heartbeat.assert_called_with("first", "first-new")
    assert [item["slug"] for item in miner.statistics()["streamers"] if item["is_active"]] == ["backup"]


def test_unauthorized_retry_uses_reloaded_session(tmp_path, monkeypatch):
    auth = VKAuth(str(tmp_path))
    session = {**SESSION, "access_token": "old", "user_agent": "test"}
    auth.save_session(session)
    api = VKApi(auth)
    module = __import__(VKApi.__module__, fromlist=["requests"])
    sent = []

    def send(method, url, *, headers, **kwargs):
        sent.append(headers["Authorization"])
        return Mock(status_code=401 if len(sent) == 1 else 200)

    def refresh(*, force):
        assert force
        auth.save_session({**session, "access_token": "new"})
        return True

    monkeypatch.setattr(module.requests, "request", send)
    monkeypatch.setattr(auth, "refresh_token_if_needed", refresh)
    response = api._request("GET", "https://example.invalid", headers=api._headers("slug"))
    assert response.status_code == 200
    assert sent == ["Bearer old", "Bearer new"]


def test_websocket_restores_pending_subscriptions_after_authentication():
    api = Mock(user_id=17)
    callback = Mock()
    client = VKWebSocket(api, callback)
    socket = Mock()
    client.ws = socket
    client.subscribe_user_channel()
    client.subscribe_channel(23)

    client._on_open(socket, "fake")
    socket.send.assert_called_once()
    client._on_message(socket, '{"id":1,"connect":{}}\n{}')
    frames = [json.loads(call.args[0]) for call in socket.send.call_args_list]
    assert frames == [
        {"id": 1, "connect": {"token": "fake", "name": "js"}},
        {"id": 2, "subscribe": {"channel": "channel-info:23"}},
        {"id": 3, "subscribe": {"channel": "users#17"}},
        {},
    ]
    client._on_message(socket, '{"push":{"channel":"users#17","pub":{"data":{"type":"bonus"}}}}')
    callback.assert_called_once_with("users#17", {"type": "bonus"})


def test_running_miner_detects_session_file_and_uses_configured_channels(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    miner = VKLiveMiner({
        "streamers": [{"slug": "first", "priority": 1}],
        "settings": {"jitter_percent": 0},
    })
    heartbeat = Event()
    bonus_claimed = Event()
    bonus_available = Event()
    session_checked = Event()
    fake_api = Mock(user_id=17)
    fake_api.get_user_info.return_value = {"id": 17}
    fake_api.check_stream_status.return_value = {
        "stream_id": "first-stream", "title": "A stream", "viewers": 1,
    }
    fake_api.get_channel_info.return_value = {"id": 23}
    fake_api.get_points_balance.return_value = 27
    fake_api.get_pending_bonus.side_effect = (
        lambda slug: "first-bonus" if bonus_available.is_set() else None
    )
    fake_api.claim_bonus.side_effect = lambda *_: bonus_claimed.set() or True

    def send(slug, stream_id):
        heartbeat.set()
        return True

    fake_api.send_heartbeat.side_effect = send
    miner.api = fake_api
    fake_socket = Mock()
    monkeypatch.setattr(
        "VKLivePointsMiner.VKLiveMiner.VKWebSocket", lambda *_: fake_socket
    )
    monkeypatch.setattr(
        "VKLivePointsMiner.VKLiveMiner.random.uniform", lambda start, end: 0 if start == 2 else start
    )
    is_authorized = miner.auth.is_authorized

    def check_auth():
        result = is_authorized()
        session_checked.set()
        return result

    monkeypatch.setattr(miner.auth, "is_authorized", check_auth)
    worker = Thread(target=miner.start, daemon=True)
    worker.start()
    try:
        assert session_checked.wait(2)
        fake_api.get_user_info.assert_not_called()
        miner.auth.save_session(SESSION)
        assert heartbeat.wait(7)
        fake_api.send_heartbeat.assert_called_once_with("first", "first-stream")
        fake_socket.subscribe_channel.assert_called_once_with(23)
        assert miner.statistics()["streamers"][0]["is_active"]
        bonus_available.set()
        miner._on_ws_message("users#17", {"type": "bonus", "channelSlug": "first"})
        assert bonus_claimed.wait(2)
        fake_api.claim_bonus.assert_called_once_with("first", "first-bonus")
    finally:
        miner.stop()
        worker.join(3)
    assert not worker.is_alive()
    fake_socket.close.assert_called_once()
    fake_api.stop_heartbeat.assert_called_once_with("first", "first-stream")


def test_miner_checks_offline_channel_bonuses_without_websocket_events(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    miner = VKLiveMiner({
        "streamers": [{"slug": "offline"}],
        "settings": {"bonus_poll_interval": 0.05},
    })
    miner.auth.save_session(SESSION)
    miner.api = Mock(user_id=17)
    miner.api.check_stream_status.return_value = None
    miner.api.get_channel_info.return_value = {"id": 23}
    miner.api.get_points_balance.return_value = 50
    bonuses = iter(["before-start", None, "while-offline"])
    miner.api.get_pending_bonus.side_effect = lambda slug: next(bonuses, None)
    both_claimed = Event()

    def claim(slug, bonus_id):
        if bonus_id == "while-offline":
            both_claimed.set()
        return True

    miner.api.claim_bonus.side_effect = claim
    monkeypatch.setattr("VKLivePointsMiner.VKLiveMiner.VKWebSocket", lambda *_: Mock())
    worker = Thread(target=miner.start, daemon=True)
    worker.start()
    try:
        assert both_claimed.wait(3)
    finally:
        miner.stop()
        worker.join(3)

    assert not worker.is_alive()
    assert [call.args for call in miner.api.claim_bonus.call_args_list] == [
        ("offline", "before-start"), ("offline", "while-offline"),
    ]
    miner.api.send_heartbeat.assert_not_called()
    assert miner.statistics()["streamers"][0]["points"] == 50
