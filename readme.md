# airband_ai

AI-assisted VHF airband monitoring system designed for 24/7 unattended operation
on Raspberry Pi.

This project intentionally avoids treating AI as a black box and focuses on:
- deterministic preprocessing (VAD)
- strict cost control (fail-fast circuit breaker)
- systemd-based reliability
- real SDR workflows in production environments

---

## Overview

airband_ai continuously monitors VHF airband audio captured by RTLSDR-Airband,
filters noise-only recordings, and transcribes meaningful radio communications
using the Gemini API.

The system is designed to:
- run continuously without human supervision
- avoid unnecessary API usage
- stop safely when cost limits are exceeded
- preserve logs and data for later inspection

---

## Architecture

```
RTL-SDR
  |
  v
RTLSDR-Airband (submodule)
  |
  v
RAM Disk (/dev/shm/airband_ai_proc)
  |
  v
airband_ai (main.py)
  ├─ VAD (vad_filter.py)
  ├─ Cost Guard (cost_guard.py)
  ├─ Gemini API
  |
  +--> transcripts/YYYY-MM-DD/*.txt
  +--> recording/processed/*.mp3
  |
  +--> Discord (emergency only)
```

---

## Key Design Decisions

### RAM Disk Usage

Incoming audio files are written to a RAM disk:

```
/dev/shm/airband_ai_proc
```

Reasons:
- avoid SD card wear
- faster I/O
- corrupted temporary files are discarded on reboot

---

### Custom VAD (No Whisper)

This project does not use Whisper locally.

Reasons:
- Raspberry Pi CPU and RAM constraints
- long inference time
- system instability under load

Instead, a lightweight RMS-based VAD is used to:
- discard silence and noise-only recordings
- reduce API usage
- keep behavior deterministic

---

### Cost Guard (Fail-Fast)

API usage is strictly controlled by cost_guard.py.

- daily cost is tracked persistently
- once the configured limit is exceeded:
  - a Discord notification is sent
  - the process exits immediately (exit code 42)
  - systemd prevents restart

This guarantees no runaway billing.

---

### systemd-First Design

The application does not attempt self-recovery.

Responsibilities are clearly separated:
- application: detect abnormal states and exit
- systemd: restart, stop, or hold the service

This keeps failure modes explicit and predictable.

---

## Repository Structure

```
airband_ai/
├─ main.py
├─ vad_filter.py
├─ cost_guard.py
├─ run_loop.sh
├─ requirements-min.txt
├─ README.md
├─ src/
│  └─ RTLSDR-Airband/   (git submodule)
```

Notes:
- src/RTLSDR-Airband is managed as a git submodule
- runtime artifacts are intentionally excluded from Git

---

## Installation

### Clone with submodule

```
git clone --recurse-submodules https://github.com/your-account/airband_ai.git
cd airband_ai
```

If already cloned:

```
git submodule update --init --recursive
```

---

### OS Dependencies

```
sudo apt update
sudo apt install -y ffmpeg
```

---

### Python Environment

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-min.txt
```

---

## Configuration

Runtime secrets are not stored in the repository.

Recommended location:

```
/etc/airband_ai/airband_ai.env
```

Example:

```
GEMINI_API_KEY=your_api_key_here
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

---

## systemd Example

```
[Unit]
Description=Airband AI (VHF Airband Transcription Daemon)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=yuki
Group=yuki
WorkingDirectory=/home/yuki/projects/airband_ai
EnvironmentFile=/etc/airband_ai/airband_ai.env

ExecStart=/home/yuki/projects/airband_ai/venv/bin/python3 \
  /home/yuki/projects/airband_ai/main.py \
  --input_dir /dev/shm/airband_ai_proc \
  --output_dir /home/yuki/projects/airband_ai/recording/processed

Restart=on-failure
RestartPreventExitStatus=42
RestartSec=10

[Install]
WantedBy=multi-user.target
```

---

## Emergency Detection

Discord notifications are sent only when emergency-like content is detected:
- 121.5 MHz
- Mayday / Pan-pan
- Squawk 7700

Routine traffic does not generate notifications.

---

## Legal Notice

This project is for educational and experimental purposes only.
Users are responsible for complying with local radio and privacy laws.

---

## License

MIT License
