"""VK Live WebSocket client (Centrifugo v2)."""

import json
import logging
import threading

import websocket

from ..constants import VK_LIVE_BASE, VK_WS_URL

logger = logging.getLogger(__name__)


class VKWebSocket:
    def __init__(self, api, on_message_callback):
        self.api = api
        self.on_message = on_message_callback
        self.ws = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._ready = False
        self._desired = set()
        self._command_id = 1

    def connect(self):
        threading.Thread(target=self._run, name="VKWebSocket", daemon=True).start()

    def _run(self):
        delay = 1
        while not self._stop.is_set():
            try:
                token = self.api.get_ws_token()
                with self._lock:
                    if self._stop.is_set():
                        return
                    self._ready = False
                    self._command_id = 1
                    self.ws = websocket.WebSocketApp(
                        VK_WS_URL,
                        header={"User-Agent": self.api.session_data["user_agent"]},
                        on_open=lambda ws: self._on_open(ws, token),
                        on_message=self._on_message,
                        on_error=self._on_error,
                    )
                self.ws.run_forever(origin=VK_LIVE_BASE, ping_interval=30, ping_timeout=10)
                if self._ready:
                    delay = 1
            except Exception as error:
                logger.warning("WebSocket connection failed: %s", error)
            finally:
                with self._lock:
                    self._ready = False
            self._stop.wait(delay)
            delay = min(delay * 2, 30)

    def _on_open(self, ws, token):
        with self._lock:
            if self._stop.is_set():
                ws.close()
                return
            self._send(ws, "connect", {"token": token, "name": "js"})

    def _on_message(self, ws, message):
        for line in message.splitlines():
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if not isinstance(data, dict):
                continue
            if data == {}:
                ws.send("{}")
            elif data.get("id") == 1:
                if "connect" not in data:
                    logger.warning("WebSocket authentication rejected")
                    ws.close()
                    return
                with self._lock:
                    self._ready = True
                    for channel in sorted(self._desired):
                        self._send(ws, "subscribe", {"channel": channel})
                logger.info("WebSocket authenticated")
            elif "error" in data:
                logger.warning("WebSocket command rejected: %s", data["error"])
            elif isinstance(data.get("push"), dict):
                push = data["push"]
                channel = push.get("channel")
                publication = push.get("pub")
                if isinstance(channel, str) and isinstance(publication, dict):
                    payload = publication.get("data")
                    if isinstance(payload, dict):
                        self.on_message(channel, payload)

    def _on_error(self, ws, error):
        if not self._stop.is_set():
            logger.warning("WebSocket error: %s", error)

    def subscribe_user_channel(self):
        if self.api.user_id:
            self._set_subscription(f"users#{self.api.user_id}", subscribe=True)

    def subscribe_channel(self, channel_id):
        self._set_subscription(f"channel-info:{channel_id}", subscribe=True)

    def unsubscribe_channel(self, channel_id):
        self._set_subscription(f"channel-info:{channel_id}", subscribe=False)

    def _set_subscription(self, channel, *, subscribe):
        with self._lock:
            if subscribe == (channel in self._desired):
                return
            if subscribe:
                self._desired.add(channel)
            else:
                self._desired.discard(channel)
            if self._ready:
                command = "subscribe" if subscribe else "unsubscribe"
                try:
                    self._send(self.ws, command, {"channel": channel})
                except websocket.WebSocketException as error:
                    logger.warning("Could not send WebSocket subscription command: %s", error)

    def _send(self, ws, command, payload):
        ws.send(json.dumps({command: payload, "id": self._command_id}))
        self._command_id += 1

    def close(self):
        self._stop.set()
        with self._lock:
            ws = self.ws
        if ws:
            ws.close()
