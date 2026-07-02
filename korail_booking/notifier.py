# -*- coding: utf-8 -*-
"""알림 모듈 — 텔레그램 메시지 + ntfy 폰 푸시.

두 채널 모두 선택적으로 켤 수 있고, 하나가 실패해도 나머지는 계속 시도합니다.
알림 전송 실패가 예매 로직을 멈추지 않도록 예외는 삼켜서 로그로만 남깁니다.
"""
from __future__ import annotations

import logging

import requests

log = logging.getLogger("korail_booking.notifier")

TIMEOUT = 10


class Notifier:
    def __init__(self, notify_cfg: dict):
        self.tg = notify_cfg.get("telegram", {}) or {}
        self.ntfy = notify_cfg.get("ntfy", {}) or {}

    def send(self, title: str, message: str) -> None:
        """모든 활성 채널로 알림을 보냅니다."""
        if self.tg.get("enabled"):
            self._send_telegram(f"*{title}*\n{message}")
        if self.ntfy.get("enabled"):
            self._send_ntfy(title, message)

    def _send_telegram(self, text: str) -> None:
        token = self.tg.get("bot_token")
        chat_id = self.tg.get("chat_id")
        if not token or not chat_id:
            log.warning("텔레그램 토큰/chat_id 가 비어 있어 건너뜁니다.")
            return
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
                timeout=TIMEOUT,
            )
            if resp.status_code != 200:
                log.warning("텔레그램 전송 실패 (%s): %s", resp.status_code, resp.text[:200])
        except requests.RequestException as e:
            log.warning("텔레그램 전송 예외: %s", e)

    def _send_ntfy(self, title: str, message: str) -> None:
        server = (self.ntfy.get("server") or "https://ntfy.sh").rstrip("/")
        topic = self.ntfy.get("topic")
        if not topic:
            log.warning("ntfy topic 이 비어 있어 건너뜁니다.")
            return
        try:
            resp = requests.post(
                f"{server}/{topic}",
                data=message.encode("utf-8"),
                headers={
                    "Title": title.encode("utf-8"),
                    "Priority": str(self.ntfy.get("priority", 5)),
                    "Tags": "train",
                },
                timeout=TIMEOUT,
            )
            if resp.status_code >= 300:
                log.warning("ntfy 전송 실패 (%s): %s", resp.status_code, resp.text[:200])
        except requests.RequestException as e:
            log.warning("ntfy 전송 예외: %s", e)
