from app.detection.detector import FraudDetector, redact_transcript
from app.llm.ollama import LlmJudgement


def test_high_risk_combination_reaches_alert_without_fake_probability() -> None:
    detector = FraudDetector()
    first = detector.analyze("请把验证码告诉我", now=1.0)
    second = detector.analyze("然后把钱转到安全账户", now=2.0)

    assert first.state in {"suspicious", "warning"}
    assert second.state in {"warning", "critical"}
    assert second.alert_active is True
    assert "critical_combination" in second.evidence_categories
    assert 0 <= second.score <= 1


def test_llm_high_confidence_semantics_can_supply_review_evidence() -> None:
    detector = FraudDetector()
    result = detector.analyze(
        "请按照刚才说的步骤继续操作",
        llm=LlmJudgement(True, 0.9, "结合上下文存在诈骗操作引导"),
        now=1.0,
    )
    assert result.llm_used is True
    assert result.state == "warning"
    assert result.alert_active is True
    assert "llm_semantic_high" in result.evidence_categories


def test_asr_homophone_plus_sharing_action_is_high_risk() -> None:
    detector = FraudDetector()

    result = detector.analyze(
        "那好吧我把我收到的衣箱码放给你",
        now=1.0,
    )

    assert result.state == "warning"
    assert result.alert_active is True
    assert "credential_code_sharing" in result.evidence_categories
    assert "衣箱码" in result.matched_terms


def test_transcript_redaction_masks_common_identifiers() -> None:
    value = redact_transcript("电话13800138000验证码123456银行卡6222021234567890123")
    assert "13800138000" not in value
    assert "123456" not in value
    assert "6222021234567890123" not in value
