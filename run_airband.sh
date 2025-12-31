#!/bin/bash

# ==========================================
# Settings: resolve paths from this script location
# ==========================================
# Resolve project root from this script location
BASE_DIR="$(cd "$(dirname "$0")" && pwd)"

SOURCE_DIR="${BASE_DIR}/recording"
# /dev/shm is the standard Linux RAM disk (fast, no extra setup).
RAM_DIR="/dev/shm/airband_ai_proc"
PROCESSED_DIR="${BASE_DIR}/recording/processed"
MAIN_SCRIPT="${BASE_DIR}/scripts/main.py"

# Max files per batch
MAX_FILES=200 

# ==========================================
# Preparation
# ==========================================
# Create the RAM working directory if missing (cleared on reboot).
if [ ! -d "$RAM_DIR" ]; then
    mkdir -p "$RAM_DIR"
fi

# ==========================================
# File move step (bug-fixed version)
# ==========================================
echo "Checking for files in $SOURCE_DIR ..."

COUNTER=0

# IMPORTANT: use process substitution instead of a pipe so COUNTER is preserved.
while read -r FILE; do
    # Max file count check
    if [ $COUNTER -ge $MAX_FILES ]; then
        echo "Batch limit ($MAX_FILES files) reached."
        break
    fi
    
    # Move files to the RAM disk
    # SD card -> RAM means mv acts as copy+delete
    mv "$FILE" "$RAM_DIR/"
    
    COUNTER=$((COUNTER + 1))

done < <(find "$SOURCE_DIR" -maxdepth 1 -type f \( -name "*.mp3" -o -name "*.wav" \))

# ==========================================
# Run Python if files exist
# ==========================================
if [ $COUNTER -eq 0 ]; then
    # No files: exit quietly
    exit 0
fi

echo "Moved $COUNTER files to RAM disk. Starting processing..."

# Run main.py
# Pass RAM dir (input) and output dir
python3 "$MAIN_SCRIPT" --input_dir "$RAM_DIR" --output_dir "$PROCESSED_DIR"

# ==========================================
# Cleanup
# ==========================================
# Clean files on the RAM disk after processing.
# (main.py should move/delete them, but this avoids leftovers.)
# Keep for debugging if needed; remove in production.
rm -rf "$RAM_DIR"/*

echo "Processing finished."
