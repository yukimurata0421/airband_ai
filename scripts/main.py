# main.py
import os
import time
import shutil
import glob
import re
import requests
from datetime import datetime
import sys
import argparse
import logging
from logging.handlers import RotatingFileHandler

import google.generativeai as genai
from dotenv import load_dotenv
from mutagen.mp3 import MP3

from cost_guard import CostCircuitBreaker
import vad_filter

# ==========================================
# Directory settings
# ==========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
TRANSCRIPTS_BASE_DIR = os.path.join(PROJECT_ROOT, "transcripts")
LOG_FILE_PATH = os.path.join(PROJECT_ROOT, "run.log")
DEFAULT_INPUT_DIR = "/dev/shm/airband_ai_proc"
DEFAULT_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "recording", "processed")

# Fallback when main.py is at the project root
if not os.path.exists(ENV_PATH):
    ENV_PATH = os.path.join(SCRIPT_DIR, ".env")
    TRANSCRIPTS_BASE_DIR = os.path.join(SCRIPT_DIR, "transcripts")
    LOG_FILE_PATH = os.path.join(SCRIPT_DIR, "run.log")

# ===== Load settings =====
load_dotenv(dotenv_path=ENV_PATH)
API_KEY = os.getenv("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

genai.configure(api_key=API_KEY)

MODEL_NAME = "gemini-2.5-flash"
generation_config = genai.GenerationConfig(
    temperature=0.0,
    max_output_tokens=4096,  # Allow longer outputs
)
model = genai.GenerativeModel(MODEL_NAME, generation_config=generation_config)

# ===== Length filter settings =====
MIN_RAW_SECONDS = 5.0
MIN_SPEECH_SECONDS = 5.0

# ===== Logger setup =====
logger = logging.getLogger("AirbandAI")
logger.setLevel(logging.INFO)
if logger.hasHandlers():
    logger.handlers.clear()

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(
    logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
)
logger.addHandler(stream_handler)

file_handler = RotatingFileHandler(
    LOG_FILE_PATH,
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding='utf-8',
)
file_handler.setFormatter(
    logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
)
logger.addHandler(file_handler)

# ★ Cost guard
breaker = CostCircuitBreaker(limit_yen=300, webhook_url=DISCORD_WEBHOOK_URL)
logger.info("=== Airband AI System Started (Daemon Mode) ===")
logger.info(f"Model: {MODEL_NAME}")
logger.info(f"CostGuard: Limit {breaker.limit_yen} JPY")

# ===== Frequency mapping =====
FREQ_LABEL_MAP = {
    "128.250": "Narita_ATIS", "121.900": "Narita_CLR", "121.950": "Narita_GND",
    "121.600": "Narita_Ramp", "118.200": "Narita_TWR_A", "118.350": "Narita_TWR_B",
    "124.400": "Narita_APP", "118.100": "Hyakuri_TWR", "120.100": "Hyakuri_APP",
    "122.000": "Ibaraki_FSC", "119.100": "Tokyo_APP_N", "124.100": "Kanto_North",
    "121.500": "Emergency",
}

# ==========================================
# Utilities
# ==========================================
def extract_freq_string(filename: str) -> str | None:
    m_dot = re.search(r'(\d{3}\.\d{1,6})', filename)
    if m_dot:
        return f"{float(m_dot.group(1)):.3f}"
    m_hz = re.search(r'(\d{9})', filename)
    if m_hz:
        return f"{int(m_hz.group(1)) / 1_000_000.0:.3f}"
    return None


def make_channel_key(filename: str) -> str:
    freq_str = extract_freq_string(filename)
    if not freq_str:
        return "unknown"
    label = FREQ_LABEL_MAP.get(freq_str)
    return f"{label}_{freq_str}MHz" if label else f"{freq_str}MHz"


def append_transcript(filepath, channel_key, text,
                      duration, speech_duration, finish_reason=None):
    """Save a Gemini response to the transcript."""
    try:
        ts = (datetime.fromtimestamp(os.path.getmtime(filepath))
              if os.path.exists(filepath) else datetime.now())
        day_dir = os.path.join(TRANSCRIPTS_BASE_DIR, ts.strftime("%Y-%m-%d"))
        os.makedirs(day_dir, exist_ok=True)
        out_path = os.path.join(day_dir, f"{channel_key}.txt")

        with open(out_path, "a", encoding="utf-8") as f:
            f.write(f"==== {ts.strftime('%H:%M:%S')} ====\n")
            f.write(f"[file] {os.path.basename(filepath)}\n")
            f.write(f"[len]  Orig:{duration:.1f}s -> Speech:{speech_duration:.1f}s\n")
            if finish_reason:
                f.write(f"[finish] {finish_reason}\n")
            f.write(text.strip() + "\n\n" + "-" * 40 + "\n\n")

    except Exception as e:
        logger.error(f"Log Append Error: {e}")


def send_discord_notification(channel_key, text, filename, duration):
    if not DISCORD_WEBHOOK_URL:
        return

    is_emergency = "121.5" in channel_key and "【緊急】" in text
    if ("Mayday" in text or "Squawk 7700" in text or "Pan-pan" in text):
        is_emergency = True

    if not is_emergency:
        return

    payload = {
        "content": "@everyone 航空無線で緊急事態を検知しました。",
        "embeds": [{
            "title": f"🚨 緊急通信受信: {channel_key}",
            "description": text[:2000],
            "color": 0xFF0000,
            "footer": {"text": f"File: {filename} ({duration:.1f}s)"},
            "timestamp": datetime.now().isoformat()
        }]
    }
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
    except Exception:
        pass


def safe_remove(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def safe_move(path, dest_dir):
    try:
        os.makedirs(dest_dir, exist_ok=True)
        shutil.move(path, os.path.join(dest_dir, os.path.basename(path)))
    except Exception:
        pass


def wait_for_file_ready(filepath):
    if not os.path.exists(filepath):
        return False
    time.sleep(1.0)

    start = time.time()
    last_size = -1
    while True:
        if not os.path.exists(filepath):
            return False
        try:
            size = os.path.getsize(filepath)
            if size == last_size and size > 0:
                return True
            last_size = size
            time.sleep(0.5)
            if time.time() - start > 10:
                return True
        except Exception:
            time.sleep(0.5)


# ==========================================
# Process a single file
# ==========================================
def process_single_file(filepath: str, processed_dir: str):
    filename = os.path.basename(filepath)
    temp_clean = filepath.replace(".mp3", "_clean.mp3")

    try:
        if not wait_for_file_ready(filepath):
            logger.warning(f"[{filename}] File vanished before ready-check")
            return

        # Cost limit
        if not breaker.can_proceed():
            logger.warning(f"🚫 Cost Limit Exceeded. Skipping {filename}")
            safe_move(filepath, processed_dir)
            return

        # Raw audio length check
        try:
            file_size = os.path.getsize(filepath)
            if file_size < 1024:
                logger.warning(f"[{filename}] Too small ({file_size} bytes).")
                safe_remove(filepath)
                return

            dur = MP3(filepath).info.length
            if dur < MIN_RAW_SECONDS:
                logger.info(f"🗑️ Too Short (Raw): {dur:.1f}s ({filename})")
                safe_remove(filepath)
                return

        except Exception as e:
            logger.error(f"[{filename}] MP3 meta read error: {e}")
            safe_remove(filepath)
            return

        # VAD processing
        clean_len, orig_len = vad_filter.remove_silence_and_save(
            filepath, temp_clean, logger=logger
        )

        if clean_len <= 0.0:
            logger.info(f"🗑️ VAD produced no speech ({filename})")
            safe_remove(filepath)
            safe_remove(temp_clean)
            return

        if clean_len < MIN_SPEECH_SECONDS:
            logger.info(f"🗑️ Too Short (After VAD): {clean_len:.1f}s ({filename})")
            safe_remove(filepath)
            safe_remove(temp_clean)
            return

        logger.info(
            f"[{filename}] Length: orig={orig_len:.1f}s, after VAD={clean_len:.1f}s"
        )

        # Send to Gemini
        logger.info(f"🚀 Uploading {os.path.basename(temp_clean)} ({clean_len:.1f}s)...")
        try:
            audio_file = genai.upload_file(temp_clean, mime_type="audio/mp3")
        except Exception as e:
            msg = str(e)
            if "timed out" in msg.lower():
                logger.warning(f"[{filename}] Upload timeout.")
            elif "429" in msg or "quota" in msg.lower():
                logger.error(f"[{filename}] Gemini quota exceeded.")
            else:
                logger.error(f"[{filename}] Upload failed: {msg}")
            safe_remove(filepath)
            safe_remove(temp_clean)
            return

        # ★ Prompt
        prompt = (
            "あなたは航空無線の文字起こしエンジンです。"
            "以下の音声は英語の航空無線交信です。\n\n"
            "【指示】\n"
            "1. 出力は次の2部構成にしてください（この順序と見出しを固定）。\n"
            "   [EN]\n"
            "   英語の交信の文字起こし\n"
            "   [JA]\n"
            "   日本語の概要（1行、短く具体的に。例: 方向指示で120の方向）\n"
            "2. 英語文字起こしは、聞き取れる単語やフレーズを可能な限り落とさず書いてください。短く要約したり省略しないでください。\n"
            "3. 交信で同じ語句が繰り返された場合は、その繰り返しもそのまま残してください。\n"
            "4. ノイズの説明や、聞き取りにくさの説明は一切書かないでください。\n"
            "5. ほとんど何も聞き取れない場合は、出力を1行だけ「UNINTELLIGIBLE」としてください（この場合は[EN]/[JA]を出さない）。\n"
            "6. 一部だけ聞き取れない場合は、その部分を短く「---」で置き換えてもよいですが、"
            "   「---」を長く繰り返したり、何十個も並べないでください。語やフレーズを丸ごと消さず、位置を保つようにしてください。\n"
            "7. 箇条書きやタイムスタンプは不要です。\n"
        )

        try:
            resp = model.generate_content([prompt, audio_file])
        except Exception as e:
            logger.error(f"[{filename}] Gemini request failed: {e}")
            try:
                audio_file.delete()
            except Exception:
                pass
            safe_remove(filepath)
            safe_remove(temp_clean)
            return

        # Get finish_reason
        finish_reason = None
        try:
            if resp.candidates:
                finish_reason = resp.candidates[0].finish_reason
        except Exception:
            pass

        # usage (token count)
        if hasattr(resp, "usage_metadata"):
            um = resp.usage_metadata
            breaker.add_cost(
                um.prompt_token_count,
                um.candidates_token_count
            )
            logger.info(
                f"💰 Cost: {breaker.total_cost:.2f} JPY "
                f"(prompt={um.prompt_token_count}, resp={um.candidates_token_count}, "
                f"finish_reason={finish_reason})"
            )

        # Extract text
        resp_text = ""
        try:
            resp_text = (getattr(resp, "text", None) or "").strip()
            if not resp_text and getattr(resp, "candidates", None):
                parts = resp.candidates[0].content.parts or []
                resp_text = "".join(getattr(p, "text", "") for p in parts).strip()
        except Exception as e:
            logger.warning(f"[{filename}] Failed to parse text: {e}")

        # MAX_TOKENS check
        if finish_reason == "MAX_TOKENS":
            logger.warning(f"[{filename}] Gemini output TRUNCATED (MAX_TOKENS)")
            resp_text += "\n\n【※Gemini出力がトークン上限で途中までの可能性があります】"

        # ===== Junk output filter =====
        if not resp_text:
            logger.warning(f"[{filename}] Empty response text.")
            try:
                audio_file.delete()
            except Exception:
                pass
            safe_remove(filepath)
            safe_remove(temp_clean)
            return

        # Only "---" and spaces / UNINTELLIGIBLE / no reception
        resp_compact = resp_text.replace("-", "").replace(" ", "").lower()
        if resp_compact in ("", "unintelligible", "受信不能"):
            logger.info(f"[{filename}] Marked as unintelligible. Skip logging.")
            try:
                audio_file.delete()
            except Exception:
                pass
            safe_remove(filepath)
            safe_remove(temp_clean)
            return

        # Skip outputs that only describe noise (legacy prompt pattern)
        junk_patterns = [
            "この音声は非常にノイズが多く",
            "英語の交信内容を認識することはできませんでした",
            "雑音に埋もれています",
        ]
        if any(pat in resp_text for pat in junk_patterns):
            logger.info(f"[{filename}] Gemini output is noise description only. Skip.")
            try:
                audio_file.delete()
            except Exception:
                pass
            safe_remove(filepath)
            safe_remove(temp_clean)
            return
        # ===== End junk output filter =====

        # Save
        channel = make_channel_key(filename)
        append_transcript(
            filepath, channel, resp_text,
            orig_len, clean_len,
            finish_reason=finish_reason
        )

        send_discord_notification(
            channel, resp_text, filename, clean_len
        )

        try:
            audio_file.delete()
        except Exception:
            pass

        safe_move(temp_clean, processed_dir)
        safe_remove(filepath)
        logger.info(f"✅ Done: {filename}")

    except Exception as e:
        logger.exception(f"Process Error on {filename}: {e}")
        safe_remove(temp_clean)
        safe_move(filepath, processed_dir)


# ==========================================
# Main loop
# ==========================================
def main_loop(input_dir, output_dir):
    logger.info(f"📂 Monitoring: {input_dir} -> {output_dir}")

    while True:
        try:
            files = glob.glob(os.path.join(input_dir, "*.mp3"))
            files.sort(key=lambda x: os.path.getmtime(x) if os.path.exists(x) else 0)

            now = time.time()
            ready = [f for f in files if now - os.path.getmtime(f) > 2.0]

            if not ready:
                time.sleep(1.0)
                continue

            for f in ready:
                process_single_file(f, output_dir)
                time.sleep(0.5)

        except KeyboardInterrupt:
            logger.info("🛑 Stopped.")
            break
        except Exception as e:
            logger.exception(f"Loop Error: {e}")
            time.sleep(5)


# ==========================================
# Entry point
# ==========================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_dir", default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output_dir", default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    os.makedirs(args.input_dir, exist_ok=True)
    os.makedirs(args.output_dir, exist_ok=True)

    try:
        main_loop(args.input_dir, args.output_dir)
    except KeyboardInterrupt:
        pass
