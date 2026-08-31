from app.asr.faster_whisper import is_transcript_usable


def test_low_confidence_transcript_is_rejected() -> None:
    assert not is_transcript_usable("背景噪声", 0.49, 0.5)
    assert is_transcript_usable("正常对话", 0.5, 0.5)
    assert is_transcript_usable("正常对话", None, 0.5)
