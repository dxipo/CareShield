# CareShield Fraud Worker

Independent, CPU-first audio fraud detection service. It reads the AAC audio
track from the authenticated CareShield media relay, performs local speech
recognition, combines deterministic fraud evidence with optional local Ollama
adjudication, and publishes canonical `fraud_detection` results through the M4
Backend pipeline.

The Worker never receives EZVIZ credentials or temporary playback addresses.
Raw audio is not persisted. Full transcripts remain in a short in-memory
context only; published previews are length-limited and identifier-redacted.

The first baseline uses the local CTranslate2 Whisper model supplied with the
research prototype. Ollama is optional: rule detection continues when its
configured model is unavailable, while runtime metadata reports that state.
