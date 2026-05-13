from __future__ import annotations
import hashlib
import os
import time
from typing import TYPE_CHECKING

from harness._core.http_session import HttpSession
from harness._core.logger import StructuredLogger

if TYPE_CHECKING:
    from harness._core.config import ConfigBase

_log = StructuredLogger("notifier")

_DEDUP_TTL_S = 3600  # 1 hour


class Notifier:
    def __init__(self, config: "ConfigBase") -> None:
        self._config = config
        self._dedup: dict[str, float] = {}

    def _dedup_key(self, msg: str) -> str:
        return hashlib.md5(msg[:100].encode(), usedforsecurity=False).hexdigest()

    def _is_duplicate(self, key: str) -> bool:
        ts = self._dedup.get(key)
        return ts is not None and (time.monotonic() - ts) < _DEDUP_TTL_S

    def notify(
        self, msg: str, severity: str = "INFO", domain: str = ""
    ) -> None:
        key = self._dedup_key(msg)
        is_critical = severity.upper() == "CRITICAL"

        if not is_critical and self._is_duplicate(key):
            _log.debug("notify deduped", key=key)
            return

        self._dedup[key] = time.monotonic()
        prefix = f"[{severity}][{domain}] " if domain else f"[{severity}] "
        full_msg = prefix + msg

        sent = False
        if not sent:
            sent = self._try_slack(full_msg, severity)
        if not sent:
            sent = self._try_github_issue(full_msg, severity)
        if not sent:
            # Final fallback — always succeeds
            _log.error(
                "notify fallback: all tiers failed, logging only",
                msg=full_msg,
            )

    def _try_slack(self, msg: str, severity: str) -> bool:
        token = os.environ.get("SLACK_BOT_TOKEN")
        channel = os.environ.get("SLACK_DM_USER_ID")
        if not token or not channel:
            return False
        try:
            session = HttpSession("https://slack.com/api")
            session._session.headers["Authorization"] = f"Bearer {token}"
            resp = session.post(
                "/chat.postMessage",
                json={"channel": channel, "text": msg},
            )
            data = resp.json()
            if data.get("ok"):
                _log.info("notify sent via Slack", severity=severity)
                return True
            _log.warning("Slack notify failed", error=data.get("error"))
            return False
        except Exception as exc:
            _log.warning("Slack notify exception", error=str(exc))
            return False

    def _try_gmail(self, msg: str, severity: str) -> bool:
        # Gmail OAuth not yet configured — implement in Phase 4
        raise NotImplementedError(
            "Gmail notifier tier is a Phase 4 TODO. "
            "Configure Gmail OAuth service account and implement here."
        )

    def _try_github_issue(self, msg: str, severity: str) -> bool:
        token = os.environ.get("GITHUB_TOKEN")
        repo = os.environ.get("GITHUB_REPOSITORY", "jisuyun-456/sincerely-scm-pipeline")
        if not token:
            return False
        try:
            session = HttpSession("https://api.github.com")
            session._session.headers.update(
                {
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                }
            )
            body = f"{msg}\n\n@jisuyun-456"
            resp = session.post(
                f"/repos/{repo}/issues",
                json={"title": f"[Harness Alert] {severity}", "body": body},
            )
            _log.info(
                "notify sent via GH Issue",
                issue_url=resp.json().get("html_url"),
            )
            return True
        except Exception as exc:
            _log.warning("GH Issue notify exception", error=str(exc))
            return False
