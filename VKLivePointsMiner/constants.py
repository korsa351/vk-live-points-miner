# VK Live API Constants

VK_LIVE_BASE = "https://live.vkvideo.ru"
VK_API_BASE = "https://api.live.vkvideo.ru"
VK_WS_URL = "wss://pubsub.live.vkvideo.ru/connection/websocket?cf_protocol_version=v2"

class Endpoint:
    """API endpoints"""

    # Авторизация и пользователь
    GET_USER = f"{VK_API_BASE}/v8/actor"
    GET_WS_TOKEN = f"{VK_API_BASE}/v8/actor/web_socket/connection"

    # Канал и стрим
    GET_CHANNEL = f"{VK_API_BASE}/v8/channel/{{slug}}"
    GET_STREAM_STATUS = f"{VK_API_BASE}/v8/channel/{{slug}}/stream/slot/default"
    STREAM_REACTION = f"{VK_API_BASE}/v8/reaction"

    # Heartbeat
    SEND_HEARTBEAT = f"{VK_API_BASE}/v8/channel/{{slug}}/stream/{{stream_id}}/heartbeat"
    STOP_HEARTBEAT = f"{VK_API_BASE}/v8/channel/{{slug}}/stream/{{stream_id}}/heartbeat?isStop=true"

    # Баллы и бонусы
    GET_POINTS = f"{VK_API_BASE}/v1/channel/{{slug}}/point"
    GET_PENDING_BONUS = f"{VK_API_BASE}/v1/channel/{{slug}}/point/pending_bonus/"
    CLAIM_BONUS = f"{VK_API_BASE}/v1/channel/{{slug}}/point/pending_bonus/{{bonus_id}}/gather"

# Обязательные заголовки для всех запросов
DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://live.vkvideo.ru",
    "X-App": "streams_web"
}

# User-Agent по умолчанию (если пользователь не предоставит свой)
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
