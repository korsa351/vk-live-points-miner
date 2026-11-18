"""Load and renew the private VK Live session file."""

import json
import logging
import os
import tempfile
import time
import urllib.parse
from pathlib import Path

import requests

from ..constants import DEFAULT_USER_AGENT, VK_LIVE_BASE

logger = logging.getLogger(__name__)
TOKEN_FIELDS = {
    "access_token": "accessToken",
    "refresh_token": "refreshToken",
    "expires_at": "expiresAt",
}


class VKAuth:
    def __init__(self, cookies_dir="cookies"):
        self.session_file = Path(cookies_dir) / "session.json"

    def is_authorized(self):
        try:
            self.load_session()
        except (OSError, ValueError):
            return False
        return True

    def load_session(self):
        with self.session_file.open(encoding="utf-8-sig") as file:
            return self._validate_session(json.load(file))

    @staticmethod
    def _validate_session(session):
        if not isinstance(session, dict) or not session.get("valid", True):
            raise ValueError("Invalid VK Live session")
        if not all(isinstance(session.get(field), str) and session[field].strip()
                   for field in ("access_token", "refresh_token", "client_id")):
            raise ValueError("VK Live tokens and client ID are required")
        expires_at = session.get("expires_at")
        if type(expires_at) is not int or expires_at <= 0:
            raise ValueError("expires_at must be a Unix timestamp in milliseconds")
        user_agent = session.get("user_agent")
        if user_agent is not None and not isinstance(user_agent, str):
            raise ValueError("Invalid user_agent")
        session["user_agent"] = user_agent or DEFAULT_USER_AGENT
        return session

    def save_session(self, session):
        self.session_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.session_file.parent, delete=False
            ) as file:
                temporary = Path(file.name)
                json.dump(session, file, indent=2, ensure_ascii=False)
                file.write("\n")
            os.replace(temporary, self.session_file)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def refresh_token_if_needed(self, *, force=False):
        session = self.load_session()
        days_until_expiry = (session["expires_at"] / 1000 - time.time()) / 86400
        if days_until_expiry > 7 and not force:
            return True

        try:
            auth_cookie = {key: session[field] for field, key in TOKEN_FIELDS.items()}
            response = requests.get(
                VK_LIVE_BASE,
                headers={"User-Agent": session["user_agent"]},
                cookies={
                    "_clientId": session["client_id"],
                    "auth": urllib.parse.quote(json.dumps(auth_cookie)),
                },
                timeout=10,
            )
            response.raise_for_status()
            for result in reversed([*response.history, response]):
                value = result.cookies.get("auth")
                if value:
                    updated = json.loads(urllib.parse.unquote(value))
                    session.update({field: updated[key] for field, key in TOKEN_FIELDS.items()})
                    self.save_session(self._validate_session(session))
                    logger.info("VK Live session refreshed")
                    return True
        except (requests.RequestException, OSError, ValueError, KeyError, TypeError):
            logger.warning("VK Live session refresh failed")
            return False

        logger.warning("VK Live did not return a refreshed session")
        return False
