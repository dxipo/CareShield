# M7 — Real-time Fraud Detection

## Runtime path

```text
H6c AAC audio
  -> authenticated Media Relay / internal RTSP
  -> Fraud Worker AudioReader
  -> 16 kHz mono PCM + endpoint segmentation
  -> local SenseVoiceSmall ONNX
  -> keyword / critical-pair / context detector
  -> optional local Ollama adjudication
  -> AlgorithmResult(fraud_detection, simulated=false)
  -> Backend -> Redis -> WebSocket -> Vue
```

The Worker receives only the internal relay address protected by the existing
AI Worker Bearer token. It never receives EZVIZ AppKey, AppSecret, AccessToken,
or an upstream playback address.

## Models

- ASR baseline: the official `iic/SenseVoiceSmall-onnx` quantized model, run
  locally through `funasr-onnx`. Chinese recognition and inverse text
  normalization are enabled. Configure its host directory with
  `FRAUD_SENSEVOICE_MODEL_HOST_PATH`. Faster-Whisper remains available only as
  an explicitly selected fallback provider.
- LLM baseline: Ollama `qwen3:4b`, stored in the `ollama_data` Docker volume.
  LLM adjudication is optional and reviews every meaningful segmented utterance;
  very short filler speech is skipped. This allows semantic evidence to recover
  from ASR misspellings even when an exact keyword rule does not match.
- The prototype Vosk directory and the two unrelated PyTorch checkpoints are
  not copied because the supplied executable script does not use them.

## Result semantics

Labels are `normal`, `suspicious`, `warning`, and `critical`. The `score` is a
bounded evidence strength, not a calibrated fraud probability. `warning` and
`critical` set `metadata.alert_active=true`; Backend stores one risk event per
alert lifecycle. Missing audio, failed ASR, or an unavailable Worker must never
be presented as `normal`.

The warning banner exposes an operator acknowledgement action. Backend forwards
it to the Fraud Worker through the authenticated internal control endpoint. An
acknowledged lifecycle stays silent while the detector remains in warning or
critical state; returning to normal rearms the next independent incident.

Credential-code sharing uses a paired rule: a security-code term (including a
small audited allow-list of observed Mandarin ASR homophones) must occur with a
sharing action such as “告诉/发给/念给”. The original transcript remains visible
unchanged; the system does not silently rewrite ASR output. High-confidence
local-LLM semantic evidence can independently raise a result for review rather
than only multiplying an already non-zero keyword score.

## Privacy

- Raw audio is decoded in memory and is not persisted.
- Full transcripts remain in a bounded, expiring in-memory context only.
- Published transcript previews are identifier-redacted and length-limited.
- No full transcript is written to application logs.
- Ollama is local by default. A future cloud provider must be explicitly
  enabled and must redact content before transmission.
- `GET /api/fraud-detection/history` returns at most 100 bounded records. Each
  record contains only the already-redacted transcript preview and an audited
  metadata allow-list; raw audio, full dialogue, LLM reasoning, and debug data
  are never persisted in this history.

## Runtime dependencies and licenses

| Component | Pinned version / model | Purpose | License |
| --- | --- | --- | --- |
| FunASR ONNX | 0.4.2 | SenseVoiceSmall local ASR runtime | MIT |
| SenseVoiceSmall ONNX | official quantized checkpoint | Chinese ASR and inverse text normalization | Apache-2.0 |
| ONNX Runtime | resolved by FunASR ONNX | CPU inference runtime | MIT |
| Faster-Whisper | 1.2.1 | Explicit fallback ASR runtime | MIT |
| PyAV | 18.1.0 | Decode and resample the relay audio track | BSD-3-Clause |
| Ollama | 0.12.11 container | Local LLM serving | MIT |
| Qwen3 | `qwen3:4b` | Optional fraud-language adjudication | Apache-2.0 |

ASR model assets are deployment-local and ignored by Git. The default model is
the official `iic/SenseVoiceSmall-onnx` quantized checkpoint. Deployers choosing
the Faster-Whisper fallback remain responsible for checking the provenance and
license of their mounted checkpoint.

## Local setup

Place the official ONNX model files under
`models/fraud/sensevoice-small-onnx/`, or configure:

```env
FRAUD_ASR_PROVIDER=sensevoice_small
FRAUD_SENSEVOICE_MODEL_HOST_PATH=/absolute/path/to/sensevoice-small-onnx
FRAUD_ASR_MODEL_PATH=/models/fraud/sensevoice-small-onnx
FRAUD_ASR_DEVICE=cpu
FRAUD_ASR_CPU_THREADS=2
FRAUD_OLLAMA_MODEL=qwen3:4b
```

The CPU baseline limits ONNX Runtime thread use so continuous ASR does not
starve the desktop browser or other CareShield services. These values are
deployment tuning controls, not inference FPS. SenseVoiceSmall is not served by
Ollama; Ollama receives only the resulting text for optional semantic review.

Install the optional local LLM model into the ignored Compose volume:

```bash
docker compose up -d ollama
docker compose exec ollama ollama pull qwen3:4b
```

Then rebuild and inspect safe runtime state:

```bash
docker compose up -d --build fraud-worker backend frontend
docker compose ps
docker compose exec fraud-worker python -c "import json,urllib.request; print(json.load(urllib.request.urlopen('http://localhost:8092/status')))"
```

The status response contains no credentials, playback URL, raw audio, or full
dialogue. Real alert validation should play legally obtained, non-sensitive
normal and scam-like speech while recording false positives, false negatives,
ASR text, and end-to-end latency.
