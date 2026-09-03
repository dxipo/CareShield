# Fraud voice alert assets

This directory is mounted read-only at `/alerts` inside Fraud Worker. After an
EZVIZ cloud-broadcast package is activated, place an operator-approved
`fraud-warning.aac` here and explicitly enable `FRAUD_VOICE_ALERT_ENABLED` in
the local `.env` file.

Audio files in this directory are ignored by Git. Use AAC mono, no longer than
60 seconds and no larger than 5 MB. Do not store household recordings here.
