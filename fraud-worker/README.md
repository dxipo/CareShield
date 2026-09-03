# CareShield Fraud Worker

Independent, CPU-first audio fraud detection service. It reads the AAC audio
track from the authenticated CareShield media relay, performs local speech
recognition, combines deterministic fraud evidence with optional local Ollama
adjudication, and publishes canonical `fraud_detection` results through the M4
Backend pipeline.

The Worker never receives EZVIZ credentials or temporary playback addresses.
Raw audio is not persisted. Full transcripts remain in a short in-memory
context only; published previews are length-limited and identifier-redacted.

The default ASR is the official SenseVoiceSmall ONNX quantized model, loaded
locally through `funasr-onnx` with Chinese recognition and inverse text
normalization enabled. The previous CTranslate2 Whisper implementation remains
an explicit fallback. Ollama is optional and only reviews recognized text; it
does not host or run SenseVoiceSmall. Rule detection continues when Ollama is
unavailable, while runtime metadata reports that state.

## Reserved camera voice alert

When a real fraud result first enters an active `warning` or `critical`
lifecycle, the Worker can send one operator-provided WAV/MP3/AAC announcement
through Backend's authenticated transient EZVIZ voice endpoint. The feature is
disabled by default because cloud-broadcast usage is billable. Repeated results
in the same lifecycle are latched, and a configurable cooldown prevents rapid
retries after recovery. Delivery failure never suppresses the fraud result.

The Worker receives neither EZVIZ credentials nor an access token. Configure
`FRAUD_VOICE_ALERT_AUDIO_PATH` only as a container-local path backed by an
operator-managed read-only mount; audio assets are not stored in Git.
