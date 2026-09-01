import asyncio
import json

import httpx
from careshield_contracts import FallRiskModelResult

from app.adapters.risk_explanation import RiskExplanationClient, deterministic_explanation


def result_payload() -> FallRiskModelResult:
    concept = {
        "predicted_level": "moderate",
        "predicted_level_id": 2,
        "probabilities": {"normal": 0.1, "mild": 0.2, "moderate": 0.6, "marked": 0.1},
        "top1_probability": 0.6,
        "second_best_probability": 0.2,
        "margin": 0.4,
    }
    normal = {
        "predicted_level": "normal",
        "predicted_level_id": 0,
        "probabilities": {"normal": 0.8, "abnormal": 0.2},
        "top1_probability": 0.8,
        "second_best_probability": 0.2,
        "margin": 0.6,
    }
    return FallRiskModelResult.model_validate(
        {
            "model": {
                "profile_id": "test",
                "display_name": "test",
                "status": "active",
                "architecture": "test",
                "training_scope": "test",
                "checkpoint_epoch": 1,
                "web_interface_compatible": True,
                "clinical_risk_calibrated": False,
            },
            "metadata": {
                "window_count": 6,
                "risk_classification": {
                    "thresholds": {"low_medium": 0.02, "medium_high": 0.05}
                },
            },
            "healthy_distance": 0.03,
            "risk_level": "medium",
            "concepts": {"step_length": concept, "foot_lift": normal},
            "explanation": "old list",
        }
    )


def test_deterministic_explanation_is_natural_and_fact_grounded() -> None:
    explanation = deterministic_explanation(result_payload())
    assert "本次跌倒风险评估结果为中风险" in explanation
    assert "步幅呈中度异常" in explanation
    assert "足部抬升" in explanation
    assert "MotionCLIP 健康参考偏离度为 0.030000" in explanation
    assert "0.020000–0.050000" in explanation
    assert "概念分类置信度 60.0%" in explanation
    assert "八项模型概念：" not in explanation


def test_ollama_only_renders_language_and_keeps_authoritative_result() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["think"] is False
        assert body["options"]["temperature"] == 0.0
        assert body["format"]["required"] == ["summary", "recommendation"]
        return httpx.Response(
            200,
            json={
                "response": json.dumps(
                    {
                        "summary": "本次运动表现的主要变化集中在前向推进幅度与步幅控制，提示行走推进模式相对健康参考出现偏离。与此同时，摆动期足部清障能力保持相对稳定，说明当前变化并非覆盖所有运动环节。综合来看，需要结合连续评估观察步幅控制变化是否稳定存在，并关注不同采集条件对结果的影响。",
                        "recommendation": "建议在相同拍摄距离、行走路线和速度要求下进行规范复测，并结合近期活动能力、既往情况及专业人员意见持续关注行走安全。",
                    },
                    ensure_ascii=False,
                )
            },
        )

    async def run() -> None:
        client = RiskExplanationClient(
            enabled=True,
            base_url="http://ollama.test",
            model="qwen-test",
            timeout_seconds=1,
            transport=httpx.MockTransport(handler),
        )
        original = result_payload()
        rendered = await client.explain(original)
        assert rendered.risk_level == original.risk_level
        assert rendered.healthy_distance == original.healthy_distance
        assert rendered.metadata["explanation_generation"]["llm_used"] is True
        assert "前向推进幅度与步幅控制" in rendered.explanation
        assert "【关键运动证据】" in rendered.explanation
        await client.close()

    asyncio.run(run())


def test_untrusted_numeric_llm_output_falls_back_without_failing_result() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "response": json.dumps(
                    {
                        "summary": "模型判断跌倒概率为百分之九十，需要立即确诊。",
                        "recommendation": "立即治疗。",
                    },
                    ensure_ascii=False,
                )
            },
        )

    async def run() -> None:
        client = RiskExplanationClient(
            enabled=True,
            base_url="http://ollama.test",
            model="qwen-test",
            timeout_seconds=1,
            transport=httpx.MockTransport(handler),
        )
        rendered = await client.explain(result_payload())
        assert rendered.metadata["explanation_generation"]["llm_used"] is False
        assert "百分之九十" not in rendered.explanation
        assert "立即确诊" not in rendered.explanation
        assert "步幅呈中度异常" in rendered.explanation
        await client.close()

    asyncio.run(run())
