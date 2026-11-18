"""Read-only public dashboard."""

from pathlib import Path

from flask import Flask, jsonify, send_from_directory

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"


class VKWebServer:
    def __init__(self, miner):
        self.miner = miner
        self.app = Flask(__name__, static_folder=WEB_ROOT / "static")
        self.app.add_url_rule("/", view_func=self.index)
        self.app.add_url_rule("/api/status", view_func=self.status)

    def index(self):
        return send_from_directory(WEB_ROOT, "index.html")

    def status(self):
        response = jsonify(self.miner.statistics())
        response.cache_control.no_store = True
        return response
