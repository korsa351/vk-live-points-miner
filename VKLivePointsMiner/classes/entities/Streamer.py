"""Streamer entity"""

import time


class Streamer:
    """Представляет стримера на VK Live"""

    def __init__(self, username: str, priority: int = 999, settings: dict = None):
        self.username = username  # slug канала
        self.priority = priority
        self.settings = settings or {}

        # Информация о стриме
        self.is_online = False
        self.stream_id = None
        self.title = ""
        self.viewers = 0

        # Статистика
        self.points = None
        self.watch_time = 0  # в секундах
        self.last_heartbeat = None

        # Метаданные канала
        self.channel_id = None
        self.channel_info = None

    def __repr__(self):
        status = "ONLINE" if self.is_online else "OFFLINE"
        return f"<Streamer {self.username} [{status}] Priority:{self.priority} Points:{self.points}>"

    def update_watch_time(self):
        """Обновить время просмотра"""
        now = time.monotonic()
        if self.last_heartbeat is not None:
            self.watch_time += now - self.last_heartbeat
        self.last_heartbeat = now
