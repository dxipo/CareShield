# M7 — Real-time Fraud Detection

## Runtime path

```text
H6c AAC audio
  -> authenticated Media Relay / internal RTSP
  -> Fraud Worker AudioReader
  -> 16 kHz mono PCM + endpoint segmentation
  -> local Faster-Whisper
  -> keyword / critical-pair / context detector
  -> optional local Ollama adjudication
  -> AlgorithmResult(fraud_detection, simulated=false)
  -> Backend -> Redis -> WebSocket -> Vue
```

The Worker receives only the internal relay address protected by the existing
AI Worker Bearer token. It never receives EZVIZ AppKey, AppSecret, AccessToken,
or an upstream playback address.

## Models

- ASR baseline: the local CTranslate2 Whisper asset supplied by the research
  prototype. Configure its host directory with `FRAUD_ASR_MODEL_HOST_PATH`.
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

## Runtime dependencies and licenses

| Component | Pinned version / model | Purpose | License |
| --- | --- | --- | --- |
| Faster-Whisper | 1.2.1 | Local ASR runtime | MIT |
| CTranslate2 | resolved by Faster-Whisper | Optimized Whisper inference | MIT |
| PyAV | 18.1.0 | Decode and resample the relay audio track | BSD-3-Clause |
| Ollama | 0.12.11 container | Local LLM serving | MIT |
| Qwen3 | `qwen3:4b` | Optional fraud-language adjudication | Apache-2.0 |

The Whisper model asset is deployment-local and ignored by Git. Deployers are
responsible for verifying the license of the particular Whisper checkpoint
they mount; the source prototype did not include reliable provenance metadata.

## Local setup

Place the CTranslate2 model under `models/fraud/whisper-model/`, or configure:

```env
FRAUD_ASR_MODEL_HOST_PATH=/absolute/path/to/whisper-model
FRAUD_ASR_DEVICE=cpu
FRAUD_ASR_COMPUTE_TYPE=int8
FRAUD_ASR_CPU_THREADS=2
FRAUD_ASR_NUM_WORKERS=1
FRAUD_OLLAMA_MODEL=qwen3:4b
```

The CPU baseline deliberately limits CTranslate2 to two threads and one worker
so continuous ASR does not starve the desktop browser or the other CareShield
services. These values are deployment tuning controls, not inference FPS.

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
