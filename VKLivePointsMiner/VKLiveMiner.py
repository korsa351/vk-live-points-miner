"""Runtime and configuration for VK Live Points Miner."""

import logging
import math
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from queue import SimpleQueue

from .classes.VKAuth import VKAuth
from .classes.VKApi import VKApi
from .classes.VKWebSocket import VKWebSocket
from .classes.entities.Streamer import Streamer

logger = logging.getLogger(__name__)


class VKLiveMiner:
    def __init__(self, config):
        self.auth = VKAuth()
        self.api = VKApi(self.auth)
        self.ws = None
        self.streamers = [
            Streamer(item["slug"], item.get("priority", 999))
            for item in config.get("streamers", [])
        ]
        self.active_slots = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._events = SimpleQueue()
        settings = config.get("settings", {})
        self.max_active_slots = min(2, max(1, int(settings.get("max_active_slots", 2))))
        self.monitor_interval = float(settings.get("monitor_interval", 120))
        self.heartbeat_interval = float(settings.get("heartbeat_interval", 60))
        self.jitter = float(settings.get("jitter_percent", 10)) / 100
        intervals = (self.monitor_interval, self.heartbeat_interval)
        if not all(math.isfinite(interval) and interval > 0 for interval in intervals):
            raise ValueError("Monitor and heartbeat intervals must be positive, finite numbers")
        if not 0 <= self.jitter < 1:
            raise ValueError("jitter_percent must be in [0, 100)")

    def statistics(self):
        with self._lock:
            channels = [{
                "slug": streamer.username,
                "is_online": streamer.is_online,
                "is_active": streamer in self.active_slots,
                "viewers": streamer.viewers,
                "points": streamer.points,
                "watch_time": streamer.watch_time,
            } for streamer in self.streamers]
            return {
                "total_streamers": len(channels),
                "online_count": sum(channel["is_online"] for channel in channels),
                "active_count": sum(channel["is_active"] for channel in channels),
                "streamers": channels,
            }

    def start(self):
        """Keep the panel available while waiting for authorization."""
        logger.info("Using VK Live session file %s", self.auth.session_file)
        try:
            while not self._stop.is_set():
                self._wake.clear()
                if self.auth.is_authorized():
                    try:
                        self.api.session_data = self.auth.load_session()
                        self.api.get_user_info()
                        break
                    except Exception as error:
                        logger.warning("Could not verify the VK session: %s", error)
                self._wake.wait(5)

            if self._stop.is_set():
                return

            logger.info("Logged in as user ID %s", self.api.user_id)
            self.ws = VKWebSocket(self.api, self._on_ws_message)
            self.ws.subscribe_user_channel()
            self.ws.connect()
            with ThreadPoolExecutor(max_workers=1, thread_name_prefix="ChannelMonitor") as monitor:
                self._run(monitor)
        finally:
            if self.ws:
                self.ws.close()
            for streamer, stream_id in self.active_slots.items():
                self.api.stop_heartbeat(streamer.username, stream_id)
            with self._lock:
                self.active_slots.clear()

    def stop(self):
        self._stop.set()
        self._wake.set()

    def _run(self, monitor):
        monitor_at = 0
        pending_poll = None
        refresh = False
        subscriptions = set()
        heartbeat_at = {}
        bonuses = {}
        channels = self.streamers
        while not self._stop.is_set():
            self._wake.clear()
            refresh = self._apply_events(channels, bonuses) or refresh
            if pending_poll is not None and pending_poll.done():
                self._apply_channel_status(pending_poll.result())
                pending_poll = None
                desired = {streamer.channel_id for streamer in channels if streamer.channel_id is not None}
                for channel_id in subscriptions - desired:
                    self.ws.unsubscribe_channel(channel_id)
                for channel_id in desired - subscriptions:
                    self.ws.subscribe_channel(channel_id)
                subscriptions = desired

            if pending_poll is None and (time.monotonic() >= monitor_at or refresh):
                pending_poll = monitor.submit(self._poll_channels, channels)
                pending_poll.add_done_callback(lambda _: self._wake.set())
                refresh = False
                monitor_at = time.monotonic() + self._interval(self.monitor_interval)

            if self._stop.is_set():
                break

            for streamer in self._update_active_slots():
                heartbeat_at.pop(streamer, None)

            for streamer, stream_id in self.active_slots.items():
                if self._stop.is_set():
                    break
                if time.monotonic() >= heartbeat_at.get(streamer, 0):
                    self._heartbeat(streamer, stream_id)
                    heartbeat_at[streamer] = time.monotonic() + self._interval(self.heartbeat_interval)

            for slug, due in list(bonuses.items()):
                if self._stop.is_set():
                    break
                if time.monotonic() >= due:
                    del bonuses[slug]
                    self._claim_bonus(slug)

            deadlines = [*heartbeat_at.values(), *bonuses.values()]
            if pending_poll is None:
                deadlines.append(monitor_at)
            wait = max(0, min(deadlines) - time.monotonic()) if deadlines else None
            self._wake.wait(wait)

    def _interval(self, interval):
        return interval * random.uniform(1 - self.jitter, 1 + self.jitter)

    def _poll_channels(self, channels):
        results = {}
        for streamer in channels:
            if self._stop.is_set():
                break
            try:
                results[streamer] = self.api.check_stream_status(streamer.username)
            except Exception as error:
                logger.warning("Could not check %s: %s", streamer.username, error)

            if streamer.channel_id is None and not self._stop.is_set():
                try:
                    streamer.channel_id = self.api.get_channel_info(streamer.username)["id"]
                except Exception as error:
                    logger.warning("Could not get channel ID for %s: %s", streamer.username, error)

        return results

    def _apply_channel_status(self, results):
        with self._lock:
            for streamer, info in results.items():
                streamer.is_online = bool(info)
                streamer.stream_id = info["stream_id"] if info else None
                streamer.title = info["title"] if info else ""
                streamer.viewers = info["viewers"] if info else 0

    def _update_active_slots(self):
        with self._lock:
            online = sorted(
                (streamer for streamer in self.streamers if streamer.is_online and streamer.stream_id),
                key=lambda streamer: streamer.priority,
            )
            previous = self.active_slots
            self.active_slots = {
                streamer: streamer.stream_id for streamer in online[:self.max_active_slots]
            }
            changed = {
                streamer for streamer in previous.keys() | self.active_slots.keys()
                if previous.get(streamer) != self.active_slots.get(streamer)
            }
            for streamer in changed:
                streamer.last_heartbeat = None

        for streamer in changed:
            if streamer in previous:
                self.api.stop_heartbeat(streamer.username, previous[streamer])
                logger.info("Stopped watching %s", streamer.username)
            if streamer in self.active_slots:
                logger.info("Started watching %s", streamer.username)
        return changed

    def _heartbeat(self, streamer, stream_id):
        try:
            if self.api.send_heartbeat(streamer.username, stream_id):
                with self._lock:
                    streamer.update_watch_time()
                logger.info("Heartbeat sent to %s", streamer.username)
                points = self.api.get_points_balance(streamer.username)
                with self._lock:
                    streamer.points = points
            else:
                with self._lock:
                    streamer.last_heartbeat = None
                logger.warning("Heartbeat failed for %s", streamer.username)
        except Exception as error:
            logger.warning("Could not update %s: %s", streamer.username, error)

    def _on_ws_message(self, channel, data):
        event = data.get("type", "")
        if not isinstance(event, str):
            return
        if channel.startswith("channel-info:") and event in (
            "stream_online_status", "stream_slot_online_status"
        ):
            self._events.put(("stream", data.get("blogUrl")))
        elif channel.startswith("users#") and ("bonus" in event.lower() or "reward" in event.lower()):
            self._events.put(("bonus", data.get("channelSlug") or data.get("blogUrl")))
        else:
            return
        self._wake.set()

    def _apply_events(self, channels, bonuses):
        tracked = {streamer.username for streamer in channels}
        refresh = False
        while not self._events.empty():
            event, slug = self._events.get_nowait()
            if isinstance(slug, str) and slug in tracked:
                if event == "stream":
                    refresh = True
                else:
                    bonuses.setdefault(slug, time.monotonic() + random.uniform(2, 5))
        return refresh

    def _claim_bonus(self, slug):
        with self._lock:
            streamer = next((item for item in self.streamers if item.username == slug), None)
        if streamer is None:
            return
        try:
            bonus_id = self.api.get_pending_bonus(slug)
            if bonus_id and self.api.claim_bonus(slug, bonus_id):
                logger.info("Bonus claimed on %s", slug)
                points = self.api.get_points_balance(slug)
                with self._lock:
                    streamer.points = points
        except Exception as error:
            logger.warning("Could not claim bonus for %s: %s", slug, error)
