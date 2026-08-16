from app.services.media_probe_service import MediaProbeService


def test_ffprobe_metadata_mapping_with_audio() -> None:
    result = MediaProbeService.parse_payload(
        {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "codec_long_name": "H.264 / AVC",
                    "profile": "High",
                    "width": 1920,
                    "height": 1080,
                    "pix_fmt": "yuv420p",
                    "r_frame_rate": "25/1",
                    "avg_frame_rate": "25000/1001",
                    "bit_rate": "2048000",
                    "level": 40,
                },
                {
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "sample_rate": "16000",
                    "channels": 1,
                    "channel_layout": "mono",
                    "bit_rate": "64000",
                },
            ]
        },
        device_id="ezviz_safeid",
        channel_no=1,
    )

    assert result.video is not None
    assert result.video.codec_name == "h264"
    assert result.video.width == 1920
    assert result.video.fps == 24.975
    assert result.video.pixel_format == "yuv420p"
    assert result.audio.available is True
    assert result.audio.codec_name == "aac"
    assert result.audio.sample_rate == 16000
    assert result.audio.channels == 1


def test_ffprobe_metadata_mapping_without_audio() -> None:
    result = MediaProbeService.parse_payload(
        {"streams": [{"codec_type": "video", "codec_name": "h265"}]},
        device_id="ezviz_safeid",
        channel_no=1,
    )

    assert result.video is not None
    assert result.audio.available is False
    assert result.audio.codec_name is None
