# ==========================================
# 設定
# ==========================================
BASE_DIR="/home/yuki/projects/airband_ai"
SOURCE_DIR="${BASE_DIR}/recording"
RAM_DIR="/dev/shm/airband_ai_proc"
PROCESSED_DIR="${BASE_DIR}/recording/processed"
MAIN_SCRIPT="${BASE_DIR}/scripts/main.py"
MAX_FILES=200 
TEMP_LIST="/tmp/airband_filelist.txt"

# ★重要: ライブラリが入っている仮想環境のPythonを使う
PYTHON_EXEC="${BASE_DIR}/venv/bin/python"

# もし仮想環境が見つからない場合は、システムのPythonを使う（予備）
if [ ! -f "$PYTHON_EXEC" ]; then
    PYTHON_EXEC="python3"
fi

# ==========================================
# 前準備
# ==========================================
mkdir -p "$RAM_DIR"

# ==========================================
# 1. HDDからRAMへ移動 (あれば移動する)
# ==========================================
find "$SOURCE_DIR" -maxdepth 1 -type f \( -name "*.mp3" -o -name "*.wav" \) | head -n $MAX_FILES > "$TEMP_LIST"

if [ -s "$TEMP_LIST" ]; then
    echo "Moving new files from HDD to RAM..."
    while read -r FILE; do
        mv "$FILE" "$RAM_DIR/"
    done < "$TEMP_LIST"
else
    echo "No new files in recording folder (HDD)."
fi

rm -f "$TEMP_LIST"

# ==========================================
# 2. 実行判定
# ==========================================
RAM_COUNT=$(find "$RAM_DIR" -maxdepth 1 -name "*.mp3" -o -name "*.wav" | wc -l)

if [ "$RAM_COUNT" -eq 0 ]; then
    echo "RAM disk is empty. Nothing to process. Exiting."
    exit 0
fi

# ==========================================
# 3. Pythonスクリプト実行
# ==========================================
echo "Found $RAM_COUNT files in RAM. Starting processing..."

# ★ここで正しいPythonを使う
"$PYTHON_EXEC" "$MAIN_SCRIPT" --input_dir "$RAM_DIR" --output_dir "$PROCESSED_DIR"

# ==========================================
# 後処理
# ==========================================
rm -rf "$RAM_DIR"/*
echo "Processing finished."