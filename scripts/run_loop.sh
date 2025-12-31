#!/bin/bash

# 1. Move to the script directory (avoid path issues)
cd "$(dirname "$0")"
PROJECT_ROOT="$(cd .. && pwd)"


# Use the venv Python (project-root based)
PYTHON_BIN="${PROJECT_ROOT}/venv/bin/python3"

# 2. Settings (adjust for your environment)
# Where incoming audio files appear (RAM disk, etc.)
INPUT_DIR="/dev/shm/airband_ai_proc"
# Where processed files are saved (project recording/processed)
OUTPUT_DIR="${PROJECT_ROOT}/recording/processed"

# Ensure main.py exists
if [ ! -f "main.py" ]; then
    echo "❌ エラー: main.py が見つかりません。"
    echo "run_loop.sh と同じフォルダに main.py を置いてください。"
    echo "現在の場所: $(pwd)"
    exit 1
fi

echo "=== Airband AI Loop Started ==="
echo "Working Directory: $(pwd)"
echo "Input: $INPUT_DIR"
echo "Output: $OUTPUT_DIR"

# 3. Loop
while true; do
    "$PYTHON_BIN" main.py --input_dir "$INPUT_DIR" --output_dir "$OUTPUT_DIR"
    if [ $? -eq 130 ]; then break; fi
    sleep 1
done
