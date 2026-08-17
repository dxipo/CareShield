from app.media.frame_sampler import FrameSampler


def test_sampler_uses_media_timeline_for_batched_hls_frames() -> None:
    sampler = FrameSampler(target_fps=5)

    selected = [
        timestamp
        for timestamp in (0.0, 1 / 15, 2 / 15, 3 / 15, 4 / 15, 5 / 15, 6 / 15)
        if sampler.should_sample(timestamp)
    ]

    assert selected == [0.0, 3 / 15, 6 / 15]


def test_sampler_recovers_when_stream_timeline_restarts() -> None:
    sampler = FrameSampler(target_fps=5)

    assert sampler.should_sample(100.0) is True
    assert sampler.should_sample(100.05) is False
    assert sampler.should_sample(0.0) is True
