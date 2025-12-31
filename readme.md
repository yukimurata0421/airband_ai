~~~md
# Airband AI

AI-assisted airband monitoring system designed for continuous operation on Raspberry Pi.
This project focuses on reliability, cost control, and real-world SDR workflows rather than
treating AI as a black box.

---

## Overview

- `src/RTLSDR-Airband` captures VHF airband audio and writes it to a RAM disk.
- `scripts/run_loop.sh` runs the processing loop.
- `scripts/main.py` performs VAD, sends audio to Gemini for transcription, and saves results.
- Transcripts are stored under `transcripts/YYYY-MM-DD/`.
- Optional alerts are posted to Discord for emergency-like content.

---

## Architecture

```
+----------------------+
|   RTL-SDR Dongle     |
+----------+-----------+
           |
           v
+----------------------+
|  RTLSDR-Airband      |
+----------+-----------+
           |
           v
+-------------------------------+
| RAM Disk                      |
| /dev/shm/airband_ai_proc      |
+----------+--------------------+
           |
           v
+-------------------------------+
| run_loop.sh (systemd)         |
+----------+--------------------+
           |
           v
+-------------------------------+
| main.py                       |
| - VAD                         |
| - Cost Guard                  |
| - Gemini API                  |
+----------+-----------+--------+
           |           |
           v           v
+----------------+  +------------------+
| Transcripts    |  | Processed Audio  |
| YYYY-MM-DD/    |  | recording/       |
+----------------+  +------------------+
           |
           v
+-------------------------------+
| Discord Notification (opt)    |
+-------------------------------+
```

---

## RAM Disk Usage

This project uses `/dev/shm/airband_ai_proc` as a RAM disk to reduce SD card wear,
improve I/O performance, and avoid shortening storage lifespan.

---

## Cost Guard

Cost Guard prevents unexpected API charges by tracking daily usage and stopping
processing once the limit is exceeded. If Cost Guard cannot be initialized,
the system fails fast.

---

## Why Not Whisper

Running Whisper locally on Raspberry Pi consumes significant CPU and RAM and
reduces system stability. This project intentionally offloads AI compute to
external APIs.

---

## Legal / Disclaimer

This project is for educational and experimental purposes only.
Users are responsible for complying with local radio and privacy laws.

---

## License

MIT License.
~~~
