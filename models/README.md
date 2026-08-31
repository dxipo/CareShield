# Model Artifacts

本目录用于本机模型权重和其他大体积模型产物。除本说明外，目录内容默认不提交 Git。

M7 诈骗风险基线默认从 `models/fraud/whisper-model/` 读取本地
CTranslate2 Whisper 模型，也可以在本机 `.env` 中通过
`FRAUD_ASR_MODEL_HOST_PATH` 指向其他目录。Ollama 权重保存在 Docker
Compose 的 `ollama_data` volume 中，不进入 Git。
