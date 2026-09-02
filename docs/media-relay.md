# Shared low-latency media relay

CareShield uses one EZVIZ standard-stream reader for server-side algorithms:

```text
EZVIZ HTTP-FLV (HEVC + AAC)
  -> media-relay (PyAV 18: HEVC decode + low-latency H.264 encode; AAC remux)
  -> MediaMTX RTSP path `careshield`
     |-> M5 realtime fall-detection Worker
     |-> M6 fall-risk Worker
     `-> rolling fMP4 recording (2-second segments, 2-minute retention)
```

This avoids opening competing EZVIZ sessions and lets both Workers consume the same
source timeline. Browser live view remains the official EZOPEN player because its
browser latency and controls are better suited to interactive viewing.

## Why PyAV is required

The H6c HTTP-FLV response carries HEVC with the non-standard FLV codec id 12.
Debian FFmpeg 5.1 and 7.1 report that codec as unsupported. PyAV 18.1.0 bundles a
newer FFmpeg that recognizes it. Packet-only Annex-B conversion was tested but
still produced broken HEVC reference chains after relay reconnects. The relay now
decodes the source once, waits for a clean keyframe, and encodes H.264 with
`ultrafast`/`zerolatency`, a one-second GOP and no B-frames. AAC remains packet
remuxed. Workers therefore share one stable source connection and one normalized
video timeline. Stream URLs and credentials are never logged.

## Timestamped assessment capture

MediaMTX continuously records the internal path as fMP4. When an M6 assessment is
created, `created_at` is the capture trigger. The Worker waits for the requested
duration plus segment finalization. Internally it downloads eight seconds of hidden
HEVC keyframe pre-roll before that RFC3339 trigger, decodes the dependencies, then
trims and normalizes an exact post-trigger H.264/yuv420p clip. The pre-roll never
appears in the assessment artifact or algorithm time window. This prevents an fMP4
range that begins mid-GOP from producing green frames while retaining click-time
capture semantics; capture also no longer starts from a delayed HLS playlist.

The MediaMTX RTSP, API and playback ports are private Compose-network ports. The
only relay endpoint exposed to Workers requires the existing internal Bearer token.

## Dependencies and upstream references

- [MediaMTX architecture](https://mediamtx.org/docs/features/architecture): one path can fan out a publisher to multiple readers.
- [MediaMTX recording](https://mediamtx.org/docs/features/record): fMP4 segment recording and retention.
- [MediaMTX playback](https://mediamtx.org/docs/features/playback): RFC3339 time-range retrieval.
- MediaMTX `1.20.0`, MIT license.
- PyAV `18.1.0`, BSD-3-Clause; it links to FFmpeg libraries and is used only in `media-relay`.

No playback URL, AccessToken, AppSecret, device serial, or recorded private video is
stored in Git. Rolling recordings live only in the Docker volume and expire.
