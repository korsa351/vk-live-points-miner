"""VK Live API Client"""

from typing import Optional
from threading import Lock

try:
    from curl_cffi import requests
    HAS_CURL_CFFI = True
except ImportError:
    import requests
    HAS_CURL_CFFI = False

from ..constants import Endpoint, DEFAULT_HEADERS, VK_LIVE_BASE


class VKApi:
    """HTTP клиент для работы с VK Live API"""

    def __init__(self, auth):
        self.auth = auth
        self.session_data = {}
        self._refresh_lock = Lock()
        self.user_id = None
        self.user_channel = None
        self.ws_token = None

    def _headers(self, referer_slug: Optional[str] = None) -> dict:
        """Сформировать заголовки для запроса"""
        if not self.session_data:
            self.session_data = self.auth.load_session()
        headers = DEFAULT_HEADERS.copy()
        headers["Authorization"] = f"Bearer {self.session_data['access_token']}"
        headers["User-Agent"] = self.session_data["user_agent"]
        headers["X-From-Id"] = self.session_data["client_id"]

        if referer_slug:
            headers["Referer"] = f"{VK_LIVE_BASE}/{referer_slug}"
        else:
            headers["Referer"] = VK_LIVE_BASE

        return headers

    def _request(self, method: str, url: str, **kwargs):
        """Выполнить HTTP запрос с обработкой 401"""
        kwargs.setdefault("timeout", 10)
        if HAS_CURL_CFFI:
            kwargs["impersonate"] = "chrome120"
        response = requests.request(method, url, **kwargs)
        if response.status_code != 401:
            return response

        headers = kwargs["headers"]
        with self._refresh_lock:
            self.session_data = self.auth.load_session()
            if headers["Authorization"] == self._headers()["Authorization"]:
                if not self.auth.refresh_token_if_needed(force=True):
                    return response
                self.session_data = self.auth.load_session()
            updated = self._headers()
            for name in ("Authorization", "User-Agent", "X-From-Id"):
                headers[name] = updated[name]
        return requests.request(method, url, **kwargs)

    def get_user_info(self) -> dict:
        """GET /v8/actor - получить информацию о пользователе"""
        resp = self._request("GET", Endpoint.GET_USER, headers=self._headers())
        resp.raise_for_status()
        data = self._response_data(resp.json())
        actor = data.get("actor", data)
        self.user_id = actor["id"]
        self.user_channel = actor.get("webSocketChannels", {}).get("user_private", {}).get("name")
        return actor

    def get_ws_token(self) -> str:
        """GET /v8/actor/web_socket/connection - получить JWT для WebSocket"""
        resp = self._request("GET", Endpoint.GET_WS_TOKEN, headers=self._headers())
        resp.raise_for_status()
        data = self._response_data(resp.json())
        self.ws_token = data.get("webSocketConnection", data)["token"]
        return self.ws_token

    def get_channel_info(self, slug: str) -> dict:
        """GET /v8/channel/{slug} - получить информацию о канале"""
        url = Endpoint.GET_CHANNEL.format(slug=slug)
        resp = self._request("GET", url, headers=self._headers(slug))
        resp.raise_for_status()
        data = self._response_data(resp.json())
        return data.get("channel", data)

    @staticmethod
    def _response_data(payload):
        return payload.get("data", payload) if isinstance(payload, dict) else payload

    def check_stream_status(self, slug: str) -> Optional[dict]:
        """GET /v8/channel/{slug}/stream/slot/default - проверить статус стрима"""
        url = Endpoint.GET_STREAM_STATUS.format(slug=slug)

        resp = self._request("GET", url, headers=self._headers(slug))
        resp.raise_for_status()
        if resp.status_code == 204:
            return None
        data = self._response_data(resp.json())
        stream = data.get("stream", data)
        if stream is None:
            return None
        if "status" in stream:
            if stream["status"] != "online":
                return None
        elif not stream["isOnline"]:
            return None

        return {
            "stream_id": stream.get("id") or stream["streamId"],
            "title": stream.get("title", ""),
            "viewers": (stream.get("counters") or {}).get("viewers", stream.get("viewers", 0)),
        }

    def send_heartbeat(self, slug: str, stream_id: str) -> bool:
        """PUT /v8/channel/{slug}/stream/{stream_id}/heartbeat - отправить сигнал просмотра"""
        url = Endpoint.SEND_HEARTBEAT.format(slug=slug, stream_id=stream_id)
        headers = self._headers(slug)
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        try:
            resp = self._request("PUT", url, headers=headers, data="")
            return 200 <= resp.status_code < 300
        except Exception as e:
            print(f"❌ Heartbeat error for {slug}: {e}")
            return False

    def stop_heartbeat(self, slug: str, stream_id: str) -> bool:
        """PUT .../heartbeat?isStop=true - остановить просмотр"""
        url = Endpoint.STOP_HEARTBEAT.format(slug=slug, stream_id=stream_id)
        headers = self._headers(slug)
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        try:
            resp = self._request("PUT", url, headers=headers, data="")
            return 200 <= resp.status_code < 300
        except Exception:
            return False

    def get_points_balance(self, slug: str) -> int:
        """GET /v1/channel/{slug}/point - получить баланс баллов на канале"""
        url = Endpoint.GET_POINTS.format(slug=slug)

        resp = self._request("GET", url, headers=self._headers(slug))
        resp.raise_for_status()
        data = self._response_data(resp.json())
        return data.get("channelPoint", data)["balance"]

    def get_pending_bonus(self, slug: str) -> Optional[str]:
        """GET /v1/channel/{slug}/point/pending_bonus/ - проверить наличие бонуса"""
        url = Endpoint.GET_PENDING_BONUS.format(slug=slug)

        resp = self._request("GET", url, headers=self._headers(slug))
        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return None
        data = self._response_data(resp.json())
        if isinstance(data, dict):
            if "bonuses" not in data:
                return data.get("id")
            data = data["bonuses"]
        if isinstance(data, list):
            return next((bonus["id"] for bonus in data if isinstance(bonus, dict) and bonus.get("id")), None)
        return None

    def claim_bonus(self, slug: str, bonus_id: str) -> bool:
        """PUT /v1/channel/{slug}/point/pending_bonus/{bonus_id}/gather - собрать бонус"""
        url = Endpoint.CLAIM_BONUS.format(slug=slug, bonus_id=bonus_id)
        headers = self._headers(slug)
        headers["Content-Type"] = "application/x-www-form-urlencoded"

        resp = self._request("PUT", url, headers=headers, data="")
        resp.raise_for_status()
        return 200 <= resp.status_code < 300
