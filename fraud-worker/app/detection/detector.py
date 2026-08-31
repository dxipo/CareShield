from __future__ import annotations

import re
import time
from collections import deque
from dataclasses import dataclass

from app.llm.ollama import LlmJudgement


KEYWORDS: dict[str, tuple[int, tuple[str, ...]]] = {
    "credentials": (10, ("密码", "验证码", "动态码", "安全码", "银行卡号")),
    "transfer": (10, ("转账", "汇款", "打钱", "安全账户", "转移资金")),
    "remote_control": (10, ("屏幕共享", "远程协助", "打开手机银行", "扫码支付")),
    "authority_impersonation": (
        8,
        ("涉嫌洗钱", "涉嫌犯罪", "逮捕令", "通缉令", "冻结账户", "配合调查"),
    ),
    "investment": (5, ("稳赚", "高收益", "零风险", "内部消息", "原始股", "虚拟币")),
    "health_product": (5, ("包治百病", "特效药", "神药", "无副作用", "保健品")),
    "prize_refund": (3, ("中奖", "退款链接", "双倍退", "缴纳手续费")),
    "family_impersonation": (3, ("我换号了", "急用钱", "手术费", "出事了")),
    "urgency": (3, ("立即处理", "马上", "最后机会", "否则后果", "保密")),
}

CRITICAL_PAIRS = (
    (("验证码", "密码", "动态码"), ("告诉", "提供", "发给", "念给", "输入")),
    (("转账", "汇款", "打钱"), ("安全账户", "指定账户")),
    (("屏幕共享", "远程协助"), ("手机银行", "支付宝", "微信支付")),
    (("退款", "赔付"), ("验证码", "密码", "银行卡")),
)

# Whisper can confuse short Mandarin security-code phrases with close-sounding
# words. These aliases are evidence only when a sharing verb is present in the
# same recent dialogue; the displayed transcript is never silently rewritten.
CREDENTIAL_CODE_ALIASES = (
    "验证码",
    "短信码",
    "动态码",
    "安全码",
    "衣箱码",
    "一箱码",
    "信箱码",
    "验正码",
)
CREDENTIAL_SHARE_VERBS = (
    "告诉",
    "提供",
    "发给",
    "放给",
    "念给",
    "报给",
    "发送",
    "给你",
    "给我",
)


@dataclass(frozen=True, slots=True)
class FraudDecision:
    state: str
    score: float
    evidence_categories: tuple[str, ...]
    matched_terms: tuple[str, ...]
    llm_used: bool
    llm_reason: str | None
    alert_active: bool


def redact_transcript(text: str) -> str:
    value = re.sub(r"(?<!\d)1\d{10}(?!\d)", "1**********", text)
    value = re.sub(r"(?<!\d)\d{15,19}(?!\d)", "************", value)
    value = re.sub(r"(?<!\d)\d{6}(?!\d)", "******", value)
    return value[:180]


class FraudDetector:
    """Configurable evidence score and hysteresis; score is not a probability."""

    def __init__(self, context_seconds: float = 60.0) -> None:
        self.state = "normal"
        self.score = 0.0
        self.context_seconds = context_seconds
        self._recent: deque[tuple[float, str]] = deque(maxlen=8)
        self._last_update = time.monotonic()

    @property
    def recent_dialogue(self) -> str:
        return " ".join(text for _, text in self._recent)

    def analyze(
        self,
        text: str,
        *,
        llm: LlmJudgement | None = None,
        now: float | None = None,
    ) -> FraudDecision:
        current = time.monotonic() if now is None else now
        elapsed = max(0.1, current - self._last_update)
        self._last_update = current
        self._recent.append((current, text))
        while self._recent and current - self._recent[0][0] > self.context_seconds:
            self._recent.popleft()
        context = self.recent_dialogue

        categories: list[str] = []
        terms: list[str] = []
        raw = 0.0
        for category, (weight, candidates) in KEYWORDS.items():
            hits = [word for word in candidates if word in text]
            if hits:
                categories.append(category)
                terms.extend(hits)
                raw += weight * len(hits)

        for left, right in CRITICAL_PAIRS:
            if any(word in context for word in left) and any(
                word in context for word in right
            ):
                raw += 20
                categories.append("critical_combination")
                break

        code_alias = next(
            (word for word in CREDENTIAL_CODE_ALIASES if word in context),
            None,
        )
        share_verb = next(
            (word for word in CREDENTIAL_SHARE_VERBS if word in context),
            None,
        )
        if code_alias is not None and share_verb is not None:
            # Sharing a one-time/security code is actionable high-risk evidence,
            # including a small allow-list of observed ASR homophones.
            raw += 40
            categories.append("credential_code_sharing")
            terms.extend((code_alias, share_verb))

        llm_used = llm is not None
        if llm is not None:
            if llm.suspicious and llm.confidence >= 0.8:
                raw += 40
                categories.append("llm_semantic_high")
            elif llm.suspicious and llm.confidence >= 0.55:
                raw += 20
                categories.append("llm_semantic_review")
            elif not llm.suspicious and llm.confidence >= 0.7:
                raw *= 0.8

        if raw > 0:
            self.score = self.score * max(0.90, 1.0 - elapsed / 120.0) * 0.45
            self.score += min(raw, 55.0) * 0.55
        else:
            self.score *= max(0.0, 1.0 - elapsed / 30.0)
        self.score = max(0.0, min(100.0, self.score))
        self._transition()

        return FraudDecision(
            state=self.state,
            score=self.score / 100.0,
            evidence_categories=tuple(dict.fromkeys(categories)),
            matched_terms=tuple(dict.fromkeys(terms)),
            llm_used=llm_used,
            llm_reason=llm.reason if llm is not None else None,
            alert_active=self.state in {"warning", "critical"},
        )

    def _transition(self) -> None:
        if self.state == "critical":
            if self.score < 28:
                self.state = "warning"
            return
        if self.state == "warning":
            if self.score >= 38:
                self.state = "critical"
            elif self.score < 10:
                self.state = "normal"
            return
        if self.score >= 38:
            self.state = "critical"
        elif self.score >= 22:
            self.state = "warning"
        elif self.score >= 10:
            self.state = "suspicious"
        else:
            self.state = "normal"
