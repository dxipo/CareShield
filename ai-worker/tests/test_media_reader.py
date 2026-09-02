from datetime import datetime

from app.media.reader import _PyAvSession


class FakeStream:
    average_rate = 15


class FakeFrame:
    def __init__(self, marker: str, *, key_frame: bool, is_corrupt: bool = False):
        self.marker = marker
        self.key_frame = key_frame
        self.is_corrupt = is_corrupt
        self.time = 1.0
        self.width = 1920
        self.height = 1080

    def to_ndarray(self, *, format: str):
        assert format == "bgr24"
        return self.marker


def session_with(*frames: FakeFrame) -> _PyAvSession:
    session = _PyAvSession.__new__(_PyAvSession)
    session._stream = FakeStream()
    session._frames = iter(frames)
    session._synchronized = False
    return session


def test_reader_waits_for_clean_keyframe_before_exposing_video() -> None:
    session = session_with(
        FakeFrame("dependent", key_frame=False),
        FakeFrame("corrupt", key_frame=True, is_corrupt=True),
        FakeFrame("clean-idr", key_frame=True),
        FakeFrame("clean-p", key_frame=False),
    )

    first = session.next_frame()
    second = session.next_frame()

    assert first is not None and first.image == "clean-idr"
    assert second is not None and second.image == "clean-p"
    assert isinstance(first.captured_at, datetime)


def test_corrupt_frame_rearms_keyframe_gate() -> None:
    session = session_with(
        FakeFrame("first-idr", key_frame=True),
        FakeFrame("corrupt-p", key_frame=False, is_corrupt=True),
        FakeFrame("dependent", key_frame=False),
        FakeFrame("recovery-idr", key_frame=True),
    )

    assert session.next_frame().image == "first-idr"
    assert session.next_frame().image == "recovery-idr"
