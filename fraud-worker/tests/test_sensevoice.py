import sys
from dataclasses import replace
from types import ModuleType

import numpy as np
import pytest

from app.asr.contracts import AsrError
from app.asr.factory import build_asr
from app.asr.sensevoice import SenseVoiceSmallAsr
from app.core.config import load_settings


def install_fake_funasr(monkeypatch, captured: dict) -> None:
    package = ModuleType("funasr_onnx")
    utils = ModuleType("funasr_onnx.utils")
    postprocess = ModuleType("funasr_onnx.utils.postprocess_utils")

    class FakeSenseVoiceSmall:
        def __init__(self, model_path: str, **kwargs: object) -> None:
            captured.update(model_path=model_path, **kwargs)

        def __call__(self, audio: np.ndarray, **kwargs: object) -> list[str]:
            captured.update(audio=audio, inference=kwargs)
            return ["<|zh|><|NEUTRAL|><|Speech|><|withitn|> 验证码是一二三四 "]

    package.SenseVoiceSmall = FakeSenseVoiceSmall
    postprocess.rich_transcription_postprocess = lambda value: value.split(">")[-1]
    monkeypatch.setitem(sys.modules, "funasr_onnx", package)
    monkeypatch.setitem(sys.modules, "funasr_onnx.utils", utils)
    monkeypatch.setitem(sys.modules, "funasr_onnx.utils.postprocess_utils", postprocess)


def test_sensevoice_loads_quantized_cpu_model_and_applies_chinese_itn(
    monkeypatch, tmp_path
) -> None:
    captured: dict[str, object] = {}
    (tmp_path / "model_quant.onnx").write_bytes(b"test-model")
    install_fake_funasr(monkeypatch, captured)
    asr = SenseVoiceSmallAsr(str(tmp_path), "cpu", cpu_threads=2)

    asr.load()
    transcript = asr.transcribe(np.zeros(1600, dtype=np.int16).tobytes(), 16_000)

    assert captured["model_path"] == str(tmp_path)
    assert captured["device_id"] == "-1"
    assert captured["quantize"] is True
    assert captured["intra_op_num_threads"] == 2
    assert captured["inference"] == {"language": "zh", "textnorm": "withitn"}
    assert transcript.text == "验证码是一二三四"
    assert transcript.language == "zh"
    assert transcript.confidence is None


def test_sensevoice_requires_local_model_and_16khz_audio(tmp_path) -> None:
    asr = SenseVoiceSmallAsr(str(tmp_path), "cpu")
    with pytest.raises(AsrError, match="not configured"):
        asr.load()

    (tmp_path / "model_quant.onnx").write_bytes(b"test-model")
    asr._model = lambda *args, **kwargs: ["测试"]
    asr._postprocess = str
    with pytest.raises(AsrError, match="16 kHz"):
        asr.transcribe(b"\x00\x00", 8_000)


def test_asr_factory_defaults_to_sensevoice() -> None:
    settings = replace(
        load_settings(),
        asr_provider="sensevoice_small",
        asr_model_path="/models/sensevoice",
    )
    assert isinstance(build_asr(settings), SenseVoiceSmallAsr)
