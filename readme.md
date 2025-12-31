Airband AI

Airband AI is a 24/7 unattended VHF airband monitoring system designed for Raspberry Pi and real-world SDR operation.

The system continuously receives airband audio, removes noise using a lightweight VAD, transcribes speech via the Gemini API, and fails safely when limits or errors are reached.

This project intentionally avoids treating AI as a black box and instead prioritizes reliability, cost safety, and verifiable logs suitable for long-term unattended operation.

Key Features

Continuous VHF airband reception using RTL-SDR

RAM disk based audio ingestion to protect SD cards

Custom RMS-based VAD without heavy ML models

Gemini API transcription with strict cost control

Cost Circuit Breaker with fail-fast behavior

Emergency-only Discord notifications

Designed for 24/7 unattended operation

Overview

RTLSDR-Airband captures airband audio and writes MP3 files to a RAM disk.
main.py runs as a long-lived daemon under systemd.
Audio is filtered by VAD before being sent to Gemini.
Transcripts are stored by date and channel.
Emergency-like transmissions trigger Discord notifications.
When cost limits are exceeded, the system stops safely and does not restart automatically.

Architecture

RTL-SDR Dongle
→ RTLSDR-Airband
→ RAM Disk (/dev/shm/airband_ai_proc)
→ systemd (airband-ai.service)
→ main.py

VAD

Cost Guard

Gemini API
→ Transcripts (YYYY-MM-DD)
→ Processed Audio
→ Discord Notification (optional)

Directory Layout

Project directory:

/home/yuki/projects/airband_ai

main.py

cost_guard.py

vad_filter.py

venv/

transcripts/YYYY-MM-DD/

recording/processed/

run.log

System-managed directories:

Persistent state:
/var/lib/airband_ai

daily_cost.json

Runtime input (RAM disk):
/dev/shm/airband_ai_proc

RAM Disk Usage

Incoming audio files are written to /dev/shm/airband_ai_proc.

This RAM disk is used to:

Prevent SD card wear on Raspberry Pi

Improve I/O performance for frequent small audio files

Allow safe loss of input data on reboot

All persistent data such as transcripts and cost state are stored outside the RAM disk.

Cost Guard (Circuit Breaker)

Airband AI includes a hard cost circuit breaker.

The Cost Guard:

Tracks daily Gemini API usage in JPY

Persists state under /var/lib/airband_ai

Uses atomic file writes to prevent corruption

Exits with a dedicated exit code (42) when the daily limit is exceeded

When the limit is reached:

A single Discord notification is sent

The process exits safely

systemd does not restart the service

Human intervention is required to resume operation

This guarantees that runaway API costs cannot occur.

Why Not Whisper (Local ASR)

Local ASR models such as Whisper are intentionally not used.

Reasons:

High CPU and memory usage on Raspberry Pi

Reduced stability for long-term operation

Difficulty in enforcing strict cost ceilings

This project prefers lightweight local signal processing and controlled external AI usage.

Getting Started

Requirements:

Raspberry Pi with Debian-based OS

RTL-SDR dongle

rtl_airband (RTLSDR-Airband)

ffmpeg

Python 3.9 or newer

Internet connection for Gemini API

Installation

Clone the repository with submodules:

git clone --recurse-submodules https://github.com/yourname/airband_ai.git

cd airband_ai

Create virtual environment:

python3 -m venv venv
source venv/bin/activate
pip install -r requirements-min.txt

Environment Configuration

Create environment file:

sudo mkdir -p /etc/airband_ai
sudo nano /etc/airband_ai/airband_ai.env

Example contents:

GEMINI_API_KEY=your_api_key_here
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxxxx

systemd Service

Airband AI is intended to run only via systemd.

The service:

Controls restarts

Enforces Cost Guard behavior

Manages persistent state using StateDirectory

After installing the service file:

sudo systemctl daemon-reexec
sudo systemctl daemon-reload
sudo systemctl enable airband-ai.service
sudo systemctl start airband-ai.service

Check status:

systemctl status airband-ai.service
journalctl -u airband-ai.service -f

Failure Behavior (Design Contract)

Temporary API failure: logged, file skipped

Invalid audio or noise-only input: discarded by VAD

Gemini quota or cost limit exceeded: immediate safe stop

Corrupted cost state: fail fast and stop

Missing API key: fail fast on startup

There are no silent retries and no infinite restart loops.

Logging

Application logs are written to run.log with rotation.
Service lifecycle and crashes are recorded in systemd journal.

This dual logging enables both operational monitoring and post-mortem analysis.

Legal / Disclaimer

This project is for educational and experimental purposes only.

Users are responsible for complying with local radio regulations, privacy laws, and API terms of service.

Do not use this system to record or distribute sensitive communications.

License

MIT License.