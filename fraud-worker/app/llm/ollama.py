from __future__ import annotations

import json
import time
from dataclasses import dataclass

import httpx


@dataclass(frozen=True, slots=True)
class LlmJudgement:
    suspicious: bool
    confidence: float
    reason: str


class OllamaAdjudicator:
    def __init__(self, base_url: str, model: str, timeout_seconds: float) -> None:
        self.model = model
        self._client = httpx.Client(
            base_url=base_url,
            timeout=timeout_seconds,
            trust_env=False,
        )
        self.last_error: str | None = None
        self._ready_cache = False
        self._ready_checked_at = 0.0
        self._ready_cache_seconds = 30.0

    def ready(self) -> bool:
        now = time.monotonic()
        if now - self._ready_checked_at < self._ready_cache_seconds:
            return self._ready_cache
        try:
            response = self._client.get("/api/tags")
            response.raise_for_status()
            models = response.json().get("models", [])
            available = any(
                item.get("name", "").split(":")[0] == self.model.split(":")[0]
                for item in models
                if isinstance(item, dict)
            )
            self.last_error = None if available else "Configured LLM model is not installed"
            self._ready_cache = available
            self._ready_checked_at = now
            return available
        except (httpx.HTTPError, ValueError):
            self.last_error = "Local LLM service is unavailable"
            self._ready_cache = False
            self._ready_checked_at = now
            return False

    def judge(self, dialogue: str) -> LlmJudgement | None:
        if not self.ready():
            return None
        prompt = (
            "你是居家老人防诈骗复核器。区分正常通知、营销、疑似诈骗和明确诈骗。"
            "输入来自实时语音识别，可能有同音字或近音字错误；应结合上下文识别索要或分享"
            "验证码、短信码、密码、转账、安全账户、远程控制等行为。例如‘衣箱码’可能是"
            "‘验证码’的识别错误，但只有同时出现收到、告诉、发给、念给等分享语义时才算"
            "风险证据。只根据对话证据判断，不得补造事实。只输出JSON："
            '{"suspicious":true,"confidence":0.0,"reason":"简短理由"}。'
            "confidence必须在0到1之间。对话：\n" + dialogue
        )
        try:
            response = self._client.post(
                "/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    # Qwen3 enables a separate thinking stream by default.
                    # Fraud adjudication needs bounded, machine-readable JSON,
                    # so do not spend the response budget on hidden reasoning.
                    "think": False,
                    "format": "json",
                    "options": {"temperature": 0.0, "num_predict": 160},
                },
            )
            response.raise_for_status()
            value = json.loads(response.json().get("response", "{}"))
            confidence = max(0.0, min(1.0, float(value.get("confidence", 0.0))))
            self.last_error = None
            return LlmJudgement(
                suspicious=value.get("suspicious") is True,
                confidence=confidence,
                reason=str(value.get("reason", ""))[:160],
            )
        except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError):
            self.last_error = "Local LLM adjudication failed"
            return None

    def close(self) -> None:
        self._client.close()
