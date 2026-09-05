"""Fact-grounded natural-language rendering for neuromotor results.

MotionCLIP owns the distance and concept outputs. Ollama may only phrase
pre-approved biomechanical interpretations. Deterministic evidence and fallback
text keep the explanation useful even when the local LLM is unavailable.
"""

from __future__ import annotations

import json
import re

import httpx
from careshield_contracts import FallRiskModelResult


CONCEPT_LABELS = {
    "step_length": "步幅",
    "walking_speed": "行走速度",
    "foot_lift": "足部抬升",
    "arm_swing": "摆臂幅度",
    "cadence": "步频",
    "step_width": "步宽",
    "lateral_stability": "横向稳定性",
    "stoop_posture": "躯干姿势",
}
LEVEL_LABELS = {
    "normal": "正常",
    "mild": "轻度异常",
    "moderate": "中度异常",
    "marked": "显著异常",
    "abnormal": "异常",
}
REFERENCE_BAND_LABELS = {"low": "较低", "medium": "中等", "high": "较高"}
INTERPRETATION_HINTS = {
    "step_length": "反映前向推进幅度与步幅控制",
    "walking_speed": "反映整体移动能力与行走效率",
    "foot_lift": "反映摆动期足部清障能力",
    "arm_swing": "反映上下肢协调及躯干旋转配合",
    "cadence": "反映步态节律与连续性",
    "step_width": "反映支撑基底的调整方式",
    "lateral_stability": "反映横向重心控制能力",
    "stoop_posture": "反映行走过程中的躯干前倾姿态",
}
_FORBIDDEN_LLM_PATTERNS = re.compile(
    r"\d|低风险|中风险|高风险|确诊|诊断为|治愈|保证|概率|百分之|%",
)


class RiskExplanationClient:
    def __init__(
        self,
        *,
        enabled: bool,
        base_url: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.enabled = enabled
        self.model = model
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout_seconds,
            transport=transport,
            trust_env=False,
        )

    async def explain(self, result: FallRiskModelResult) -> FallRiskModelResult:
        explanation = deterministic_explanation(result)
        generation: dict[str, object] = {
            "provider": "deterministic",
            "llm_used": False,
            "model": None,
        }
        if self.enabled:
            rendered = await self._ollama_explanation(result)
            if rendered is not None:
                explanation = rendered
                generation = {
                    "provider": "ollama",
                    "llm_used": True,
                    "model": self.model,
                }
        return result.model_copy(
            update={
                "explanation": explanation,
                "metadata": {
                    **result.metadata,
                    "explanation_generation": generation,
                },
            }
        )

    async def _ollama_explanation(self, result: FallRiskModelResult) -> str | None:
        abnormal_findings: list[dict[str, str]] = []
        stable_findings: list[dict[str, str]] = []
        for name, value in result.concepts.items():
            finding = {
                "indicator": CONCEPT_LABELS.get(name, name),
                "level": LEVEL_LABELS.get(value.predicted_level, value.predicted_level),
                "meaning": INTERPRETATION_HINTS.get(name, "反映步态运动表现"),
            }
            if value.predicted_level == "normal":
                stable_findings.append(finding)
            else:
                abnormal_findings.append(finding)
        prompt = (
            "请基于异常指标之间的关系形成专业综合分析，同时说明稳定指标提供的参照信息。"
            "分析需要解释这些表现可能反映的步态控制特点，不要逐项罗列，不得超出给定含义。"
            "建议仅限规范复测、关注居家行走安全、结合既往情况或专业人员意见。事实："
            + json.dumps(
                {
                    "abnormal_findings": abnormal_findings,
                    "stable_findings": stable_findings,
                },
                ensure_ascii=False,
            )
        )
        output_schema = {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "minLength": 100, "maxLength": 500},
                "recommendation": {"type": "string", "minLength": 30, "maxLength": 220},
            },
            "required": ["summary", "recommendation"],
            "additionalProperties": False,
        }
        try:
            response = await self._client.post(
                "/api/generate",
                json={
                    "model": self.model,
                    "system": (
                        "你是智慧康养步态评估的专业中文说明生成器。只能根据给定事实组织自然语言，"
                        "不得创造症状、病史、数值、概率或临床诊断。使用审慎的‘提示’和‘可能反映’，"
                        "避免断言因果关系。综合分析应为完整段落，体现指标之间的联系而非简单罗列。"
                        "summary 和 recommendation 均不得包含数字、风险等级文字或诊断结论。"
                    ),
                    "prompt": prompt,
                    "stream": False,
                    "think": False,
                    "format": output_schema,
                    "options": {"temperature": 0.0, "num_predict": 520},
                },
            )
            response.raise_for_status()
            payload = json.loads(response.json().get("response", "{}"))
            summary = self._validated_text(payload.get("summary"), 100, 500)
            recommendation = self._validated_text(payload.get("recommendation"), 30, 220)
            if summary is None or recommendation is None:
                return None
            return authoritative_explanation(result, summary, recommendation)
        except (httpx.HTTPError, ValueError, TypeError, json.JSONDecodeError):
            return None

    @staticmethod
    def _validated_text(value: object, minimum: int, maximum: int) -> str | None:
        if not isinstance(value, str):
            return None
        text = " ".join(value.strip().split())
        if not minimum <= len(text) <= maximum or _FORBIDDEN_LLM_PATTERNS.search(text):
            return None
        return text

    async def close(self) -> None:
        await self._client.aclose()


def authoritative_explanation(
    result: FallRiskModelResult,
    summary: str,
    recommendation: str,
) -> str:
    reference_band = REFERENCE_BAND_LABELS.get(result.risk_level, "待评估")
    window_count = result.metadata.get("window_count")
    window_description = (
        f"；综合分析 {int(window_count)} 个连续动作窗口"
        if isinstance(window_count, (int, float)) and window_count > 0
        else ""
    )
    evidence = "\n".join(f"- {item}" for item in _key_evidence(result))
    return (
        f"【运动功能评估概览】\n本次分析显示相对健康参考表征的偏离程度为{reference_band}。\n\n"
        f"【量化依据】\nGAITCLIP 健康参考偏离度为 {result.healthy_distance:.6f}，"
        f"{_threshold_description(result)}{window_description}。该偏离度是相对健康参考表征的距离，"
        "不等同于跌倒概率。\n\n"
        f"【关键参数分析】\n{evidence}\n\n"
        f"【专业综合分析】\n{summary}\n\n"
        f"【建议】\n{recommendation}"
    )


def deterministic_explanation(result: FallRiskModelResult) -> str:
    abnormal: list[str] = []
    stable: list[str] = []
    abnormal_meanings: list[str] = []
    for name, value in result.concepts.items():
        label = CONCEPT_LABELS.get(name, name)
        level = LEVEL_LABELS.get(value.predicted_level, value.predicted_level)
        if value.predicted_level == "normal":
            stable.append(label)
        else:
            abnormal.append(f"{label}呈{level}")
            abnormal_meanings.append(
                INTERPRETATION_HINTS.get(name, "反映步态运动表现")
            )
    if abnormal:
        summary = (
            "模型识别到的主要变化集中在" + "、".join(abnormal[:4]) + "。"
            "这些表现可能共同提示"
            + "、".join(dict.fromkeys(abnormal_meanings[:4]))
            + "出现偏离，需要结合连续观察判断其稳定性。"
        )
    else:
        summary = "当前八项运动表现未见模型标记的明显异常。"
    if stable:
        summary += "与此同时，" + "、".join(stable[:3]) + "保持相对稳定，可作为综合判断的重要参照。"
    recommendation = (
        "建议结合近期活动能力、既往跌倒史和日常环境综合判断，并在相同采集条件下规范复测；"
        "如连续评估提示异常，应由专业人员进一步分析。"
    )
    return authoritative_explanation(result, summary, recommendation)


def _threshold_description(result: FallRiskModelResult) -> str:
    classification = result.metadata.get("risk_classification")
    if not isinstance(classification, dict):
        return "已按当前研究分级配置生成结果"
    thresholds = classification.get("thresholds")
    if not isinstance(thresholds, dict):
        return "已按当前研究分级配置生成结果"
    try:
        low_medium = float(thresholds["low_medium"])
        medium_high = float(thresholds["medium_high"])
    except (KeyError, TypeError, ValueError):
        return "已按当前研究分级配置生成结果"
    if result.risk_level == "low":
        return f"低于第一参考分界值 {low_medium:.6f}"
    if result.risk_level == "medium":
        return f"位于参考偏离区间 {low_medium:.6f}–{medium_high:.6f}"
    if result.risk_level == "high":
        return f"高于第二参考分界值 {medium_high:.6f}"
    return "已按当前研究分级配置生成结果"


def _key_evidence(result: FallRiskModelResult) -> list[str]:
    severity = {"marked": 4, "moderate": 3, "mild": 2, "abnormal": 3, "normal": 0}
    ordered = sorted(
        result.concepts.items(),
        key=lambda item: (
            severity.get(item[1].predicted_level, 1),
            item[1].top1_probability,
        ),
        reverse=True,
    )
    abnormal = [item for item in ordered if item[1].predicted_level != "normal"][:4]
    stable = [item for item in ordered if item[1].predicted_level == "normal"][:2]
    selected = abnormal + stable
    if not selected:
        return ["当前没有可用于解释的 MotionCLIP 概念输出。"]
    evidence: list[str] = []
    for name, value in selected:
        label = CONCEPT_LABELS.get(name, name)
        level = LEVEL_LABELS.get(value.predicted_level, value.predicted_level)
        meaning = INTERPRETATION_HINTS.get(name, "反映步态运动表现")
        evidence.append(
            f"{label}：{level}；概念分类置信度 {value.top1_probability * 100:.1f}%，"
            f"与次优等级区分度 {value.margin:.3f}；{meaning}。"
        )
    return evidence
