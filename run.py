#!/usr/bin/env python3
"""VK Live Points Miner entry point."""

import argparse
import json
import signal
import sys
import threading
from pathlib import Path

DEFAULT_CONFIG = Path("config.json")
BUNDLED_CONFIG = Path(__file__).resolve().with_name("config.example.json")


def main():
    parser = argparse.ArgumentParser(description="VK Live Points Miner")
    parser.add_argument("--config", type=Path, help=f"Config file (default: {DEFAULT_CONFIG})")
    parser.add_argument("--host", default="127.0.0.1", help="Dashboard bind address")
    parser.add_argument("--port", type=int, default=8080, help="Dashboard port")
    args = parser.parse_args()

    from waitress import create_server

    from VKLivePointsMiner.VKLiveMiner import VKLiveMiner
    from VKLivePointsMiner.VKWebServer import VKWebServer
    from VKLivePointsMiner.logger import configure_logging

    try:
        using_defaults = args.config is None and not DEFAULT_CONFIG.exists()
        config_path = BUNDLED_CONFIG if using_defaults else args.config or DEFAULT_CONFIG
        with config_path.open(encoding="utf-8-sig") as file:
            config = json.load(file)
        if using_defaults:
            config["streamers"] = []
        configure_logging(config.get("logging", {}))
        miner = VKLiveMiner(config)
        web = VKWebServer(miner)
        server = create_server(web.app, host=args.host, port=args.port)
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f"Startup failed: {error}", file=sys.stderr)
        return 1

    thread = threading.Thread(target=server.run, name="Dashboard", daemon=True)
    signal.signal(signal.SIGTERM, lambda *_: miner.stop())
    thread.start()
    print(f"Dashboard: http://{args.host}:{server.effective_port}", flush=True)
    try:
        miner.start()
    except KeyboardInterrupt:
        miner.stop()
    finally:
        server.close()
        thread.join(timeout=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
