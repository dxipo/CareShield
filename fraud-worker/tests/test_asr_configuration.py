import sys
from types import SimpleNamespace

from app.asr.faster_whisper import FasterWhisperAsr


def test_asr_limits_cpu_parallelism(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    class FakeWhisperModel:
        def __init__(self, model_path: str, **kwargs: object) -> None:
            captured.update(model_path=model_path, **kwargs)

    monkeypatch.setitem(
        sys.modules,
        "faster_whisper",
        SimpleNamespace(WhisperModel=FakeWhisperModel),
    )
    asr = FasterWhisperAsr(
        str(tmp_path),
        "cpu",
        "int8",
        cpu_threads=2,
        num_workers=1,
    )

    asr.load()

    assert captured["cpu_threads"] == 2
    assert captured["num_workers"] == 1
    assert captured["local_files_only"] is True
