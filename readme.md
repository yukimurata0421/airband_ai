# airband_ai

AI-assisted VHF airband monitoring system designed for continuous operation on Raspberry Pi.

This project focuses on:
- reliability over convenience
- cost control and fail-safe behavior
- real-world SDR workflows
- systemd-based 24/7 unattended operation

AI is not treated as a black box.
Pre-processing, validation, and safe shutdown are prioritized.

---

## Overview

airband_ai processes VHF airband audio captured by RTLSDR-Airband and transcribes it using the Gemini API.

The repository is structured to separate runtime scripts from configuration and assets.

Main components:
- scripts/main.py  
  Core processing logic (VAD, Gemini API, logging, filtering).
- scripts/run_loop.sh  
  Simple loop wrapper intended for systemd execution.
- src/RTLSDR-Airband  
  Upstream RTLSDR-Airband project included as a Git submodule.

Transcription results and processed audio are stored locally.
Runtime artifacts are intentionally excluded from the repository.

---

## Architecture

```text
RTL-SDR dongle
  |
  v
RTLSDR-Airband (git submodule)
  |
  v
MP3 files written to RAM disk
  Path: /dev/shm/airband_ai_proc
  |
  v
scripts/main.py
  - VAD (noise / silence removal)
  - CostGuard (daily cost limit, exit code 42)
  - Gemini API transcription
  |
  +--> transcripts/YYYY-MM-DD/*.txt
  |
  +--> recording/processed/*.mp3

Optional:
  - Discord webhook notification (emergency-like content only)
  - systemd for 24/7 operation and auto-restart
```

---

## RAM Disk Usage

Incoming audio files are expected to appear in:

/dev/shm/airband_ai_proc

This RAM disk approach:
- reduces SD card wear
- improves I/O performance
- avoids unnecessary writes for temporary files

---

## Cost Guard

CostGuard tracks daily Gemini API usage and enforces a hard cost limit.

Behavior:
- cost is tracked per day in local state
- once the limit is exceeded, the process exits immediately
- exit code: 42 (intended for systemd RestartPreventExitStatus)

This ensures:
- no unexpected API charges
- fail-fast behavior
- predictable operational cost

---

## Why Not Whisper

Offline ASR solutions such as Whisper are intentionally avoided.

Reasons:
- high CPU and RAM usage on Raspberry Pi
- reduced system stability under continuous operation
- increased complexity for recovery and monitoring

This project offloads ASR to an external API by design.

---

## Getting Started (Raspberry Pi / Debian)

### 1) Clone with submodules

git clone --recurse-submodules https://github.com/yukimurata0421/airband_ai.git
cd airband_ai

If already cloned without submodules:

git submodule update --init --recursive

---

### 2) OS dependency

ffmpeg is required for audio processing.

sudo apt update
sudo apt install -y ffmpeg

---

### 3) Python virtual environment (minimal)

python3 -m venv venv
source venv/bin/activate
pip install -r requirements-min.txt

---

### 4) Configure secrets (recommended for systemd)

Create the environment file:

/etc/airband_ai/airband_ai.env

Example:

GEMINI_API_KEY=your_api_key_here
DISCORD_WEBHOOK_URL=optional_webhook_url

---

### 5) Manual test run

For manual testing, run scripts/main.py directly:

source venv/bin/activate
python3 scripts/main.py \
  --input_dir /dev/shm/airband_ai_proc \
  --output_dir ./recording/processed

RTLSDR-Airband must be configured separately to write MP3 files into:

/dev/shm/airband_ai_proc

---

## systemd Operation

For unattended 24/7 operation, scripts/run_loop.sh is intended to be executed by systemd.

A sample systemd unit file is documented separately.
Key design points:
- automatic restart on failure
- safe shutdown when CostGuard triggers
- no dependency on interactive shells

---

## Repository Policy

The following are intentionally excluded from version control:
- virtual environments (venv/)
- environment files (.env)
- runtime logs
- transcripts and recordings
- cost tracking state

This keeps the repository reproducible and safe to publish.

---

## Known Limitations

- VAD is RMS-based and may require tuning depending on SDR gain and noise floor.
- Audio classification is conservative by design (false negatives preferred).
- No offline ASR support.

---

## License

MIT License.

This project is provided as-is for educational and experimental purposes.
Users are responsible for complying with local radio and privacy regulations.
