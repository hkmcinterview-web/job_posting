# -*- coding: utf-8 -*-
"""텔레그램 Bot API 클라이언트 — getUpdates 롱폴링 + 메시지/사진 전송/수신."""
import requests


class TelegramClient:
    def __init__(self, token: str):
        self.base = f"https://api.telegram.org/bot{token}"
        self.file_base = f"https://api.telegram.org/file/bot{token}"

    def download_file(self, file_id: str) -> bytes:
        """사용자가 보낸 사진/파일을 내려받는다 (getFile → 파일 경로 → 다운로드)."""
        r = requests.get(f"{self.base}/getFile", params={"file_id": file_id}, timeout=30)
        r.raise_for_status()
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"getFile 실패: {data}")
        file_path = data["result"]["file_path"]
        r2 = requests.get(f"{self.file_base}/{file_path}", timeout=60)
        r2.raise_for_status()
        return r2.content

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
