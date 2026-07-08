# -*- coding: utf-8 -*-
"""텔레그램 Bot API 클라이언트 — getUpdates 롱폴링 + 메시지/사진 전송."""
import requests


class TelegramClient:
    def __init__(self, token: str):
        self.base = f"https://api.telegram.org/bot{token}"

    def get_updates(self, offset=None, timeout=50):
        params = {"timeout": timeout, "allowed_updates": '["message"]'}
        if offset is not None:
            params["offset"] = offset
        r = requests.get(f"{self.base}/getUpdates", params=params, timeout=timeout + 10)
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"getUpdates 실패: {data}")
        return data.get("result", [])

    def send_message(self, chat_id, text: str):
        # 텔레그램 메시지는 4096자 제한 — 나눠서 전송
        chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)] or [""]
        for chunk in chunks:
            requests.post(
                f"{self.base}/sendMessage",
                data={"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True},
                timeout=30,
            )

    def send_photo(self, chat_id, path, caption: str = ""):
        with open(path, "rb") as f:
            requests.post(
                f"{self.base}/sendPhoto",
                data={"chat_id": chat_id, "caption": caption[:1000]},
                files={"photo": f},
                timeout=60,
            )
