import numpy as np

from app.media.segmenter import EndpointSegmenter


def pcm(value: int, samples: int) -> bytes:
    return np.full(samples, value, dtype=np.int16).tobytes()


def test_segmenter_emits_bounded_speech_after_trailing_silence() -> None:
    segmenter = EndpointSegmenter(
        sample_rate=100,
        rms_threshold=100,
        endpoint_silence_seconds=0.2,
        minimum_utterance_seconds=0.3,
        maximum_utterance_seconds=2,
    )

    assert segmenter.feed(pcm(500, 30)) is None
    utterance = segmenter.feed(pcm(0, 20))

    assert utterance is not None
    assert utterance.duration_seconds == 0.5
    assert utterance.peak_rms == 500


def test_segmenter_does_not_emit_silence() -> None:
    segmenter = EndpointSegmenter(
        sample_rate=100,
        rms_threshold=100,
        endpoint_silence_seconds=0.2,
        minimum_utterance_seconds=0.3,
        maximum_utterance_seconds=2,
    )
    for _ in range(10):
        assert segmenter.feed(pcm(0, 20)) is None
    assert segmenter.flush() is None
