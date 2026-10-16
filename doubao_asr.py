"""
Doubao (Volcengine) 大模型录音文件识别标准版 API adapter.

Submit a publicly accessible audio URL, poll the query endpoint, and return
utterance-level segments with (text, start, end) in seconds — the same shape
used by align_and_cut.cut_audio_clips().

Docs: https://www.volcengine.com/docs/6561/1354868
Resource ID for 豆包录音文件识别模型 2.0: volc.seedasr.auc
"""

import logging
import os
import time
import uuid

import requests

logger = logging.getLogger(__name__)

SUBMIT_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
QUERY_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"
RESOURCE_ID = "volc.seedasr.auc"  # 豆包录音文件识别模型 2.0

STATUS_OK = "20000000"
STATUS_PROCESSING = "20000001"
STATUS_QUEUED = "20000002"


class DoubaoASR:
    """Doubao bigmodel audio-file ASR (submit + poll)."""

    def __init__(
        self,
        app_id: str = "",
        access_token: str = "",
        api_key: str = "",
        language: str = "de-DE",
    ):
        # 旧版控制台：APP ID + Access Token；新版控制台：单个 API Key
        self.app_id = app_id or os.environ.get("DOUBAO_ASR_APP_ID", "")
        self.access_token = access_token or os.environ.get("DOUBAO_ASR_ACCESS_TOKEN", "")
        self.api_key = api_key or os.environ.get("DOUBAO_ASR_API_KEY", "")
        self.language = language or os.environ.get("DOUBAO_ASR_LANGUAGE", "de-DE")
        if not self.api_key and not (self.app_id and self.access_token):
            raise RuntimeError(
                "豆包 ASR 凭据未配置：请在管理员面板「系统设置 → 豆包 API 设置」填写"
                "（新版控制台 API Key，或旧版 APP ID + Access Token），"
                "或设置环境变量 DOUBAO_ASR_API_KEY / DOUBAO_ASR_APP_ID + DOUBAO_ASR_ACCESS_TOKEN"
            )

    def _headers(self, request_id: str, submit: bool) -> dict:
        if self.api_key:
            headers = {
                "X-Api-Key": self.api_key,
                "X-Api-Resource-Id": RESOURCE_ID,
                "X-Api-Request-Id": request_id,
            }
        else:
            headers = {
                "X-Api-App-Key": self.app_id,
                "X-Api-Access-Key": self.access_token,
                "X-Api-Resource-Id": RESOURCE_ID,
                "X-Api-Request-Id": request_id,
            }
        if submit:
            headers["X-Api-Sequence"] = "-1"
        return headers

    def _raise_status_error(self, action: str, resp: requests.Response):
        status = resp.headers.get("X-Api-Status-Code", "")
        message = resp.headers.get("X-Api-Message", "")
        logid = resp.headers.get("X-Tt-Logid", "")
        body = (resp.text or "")[:300]
        raise RuntimeError(f"Doubao {action} failed: status={status} message={message!r} logid={logid} body={body}")

    def transcribe_url(
        self,
        audio_url: str,
        audio_format: str = "mp3",
        poll_interval: float = 10.0,
        timeout: float = 3600.0,
        cancel_check=None,
        progress_callback=None,
    ) -> tuple[str, list[dict]]:
        """
        Submit the audio URL and poll until the result is ready.

        Returns (full_text, segments) where each segment is
        {"text": str, "start": float_seconds, "end": float_seconds}.
        """
        request_id = str(uuid.uuid4())
        body = {
            "user": {"uid": "anki-app"},
            "audio": {"format": audio_format, "url": audio_url},
            "request": {
                "model_name": "bigmodel",
                "enable_itn": True,
                "enable_punc": True,
                "show_utterances": True,
            },
        }
        if self.language:
            body["audio"]["language"] = self.language

        logger.info("Doubao submit: request_id=%s url=%s", request_id, audio_url)
        resp = requests.post(SUBMIT_URL, json=body, headers=self._headers(request_id, submit=True), timeout=60)
        if resp.headers.get("X-Api-Status-Code", "") != STATUS_OK:
            self._raise_status_error("submit", resp)
        logger.info("Doubao submit OK: request_id=%s", request_id)

        start = time.time()
        while True:
            if cancel_check:
                cancel_check()
            if time.time() - start > timeout:
                raise RuntimeError(f"Doubao ASR timed out after {timeout:.0f}s (request_id={request_id})")
            time.sleep(poll_interval)

            if cancel_check:
                cancel_check()
            resp = requests.post(QUERY_URL, json={}, headers=self._headers(request_id, submit=False), timeout=60)
            status = resp.headers.get("X-Api-Status-Code", "")
            if status in (STATUS_PROCESSING, STATUS_QUEUED):
                waited = time.time() - start
                logger.info("Doubao processing (request_id=%s, waited %.0fs)", request_id, waited)
                if progress_callback:
                    try:
                        progress_callback(waited)
                    except Exception:
                        pass
                continue
            if status != STATUS_OK:
                self._raise_status_error("query", resp)

            data = resp.json() or {}
            result = data.get("result") or {}
            full_text = (result.get("text") or "").strip()
            utterances = result.get("utterances") or []

            segments = []
            for u in utterances:
                text = (u.get("text") or "").strip()
                if not text:
                    continue
                segments.append({
                    "text": text,
                    "start": (u.get("start_time") or 0) / 1000.0,
                    "end": (u.get("end_time") or 0) / 1000.0,
                })

            if not segments and full_text:
                # show_utterances 未生效时兜底：整段文本作为单个 segment
                duration_ms = (data.get("audio_info") or {}).get("duration") or 0
                segments = [{"text": full_text, "start": 0.0, "end": duration_ms / 1000.0}]
            if not segments:
                raise RuntimeError("Doubao ASR returned empty result")

            logger.info("Doubao done: request_id=%s, %d segments, %.1fs total", request_id, len(segments), time.time() - start)
            return full_text, segments

    def transcribe(self, audio_path: str, language: str = "de") -> str:
        """Not supported: this engine requires a public audio URL. Use transcribe_url()."""
        raise NotImplementedError("DoubaoASR requires a public audio URL; call transcribe_url() from the worker")
