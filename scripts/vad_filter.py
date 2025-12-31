import os
from typing import Tuple, List, Optional

import numpy as np
from pydub import AudioSegment


# ===== Parameters =====
TARGET_SR = 16_000         # Analysis sample rate
FRAME_MS = 30              # Frame length (ms)
HOP_MS = 15                # Frame hop (ms)
NOISE_PERCENTILE = 20      # Below this percentile is treated as noise
THRESHOLD_MARGIN_DB = 6.0  # dB above noise floor to count as speech
MIN_SPEECH_MS = 200        # Minimum speech segment length (ms)
MIN_SILENCE_MS = 300       # Minimum silence length between segments (ms)
GAP_MERGE_MS = 300         # Merge gaps shorter than this (ms)
MIN_OUTPUT_MS = 500        # If output is shorter, treat as noise (ms)


_processed_count = 0


def _log(msg: str, logger=None) -> None:
    if logger:
        logger.info(msg)
    else:
        print(msg)


def _audiosegment_to_mono_np(seg: AudioSegment):
    """
    AudioSegment -> (mono_seg, np.float32 waveform, sample_rate)
    """
    mono = seg.set_frame_rate(TARGET_SR).set_channels(1)
    samples = np.array(mono.get_array_of_samples()).astype(np.float32)

    # Normalize amplitude to -1.0..1.0
    max_val = float(1 << (8 * mono.sample_width - 1))
    waveform = samples / max_val

    return mono, waveform, mono.frame_rate


def _compute_frame_rms_db(
    waveform: np.ndarray,
    sr: int,
    frame_ms: int = FRAME_MS,
    hop_ms: int = HOP_MS,
) -> Tuple[np.ndarray, int, int]:
    """
    Split waveform into short-time frames and compute RMS[dB].
    Returns: (dBFS per frame, frame_size, hop_size)
    """
    frame_size = int(sr * frame_ms / 1000)
    hop_size = int(sr * hop_ms / 1000)

    if frame_size <= 0 or hop_size <= 0 or len(waveform) < frame_size:
        return np.array([]), frame_size, hop_size

    num_frames = 1 + (len(waveform) - frame_size) // hop_size
    rms_list = []

    for i in range(num_frames):
        start = i * hop_size
        end = start + frame_size
        frame = waveform[start:end]

        if frame.size == 0:
            rms_list.append(-120.0)
            continue

        rms = np.sqrt(np.mean(frame ** 2) + 1e-12)
        db = 20 * np.log10(rms + 1e-12)  # Approx dBFS
        rms_list.append(db)

    return np.array(rms_list, dtype=np.float32), frame_size, hop_size


def _detect_speech_regions(
    frame_db: np.ndarray,
    frame_ms: int,
    hop_ms: int,
    total_ms: int,
) -> List[Tuple[int, int]]:
    """
    Determine speech frames from per-frame dB and return [start_ms, end_ms].

    - Estimate noise floor by percentile
    - Threshold is noise_floor + THRESHOLD_MARGIN_DB
    """
    if frame_db.size == 0:
        return []

    # Estimate noise floor
    noise_floor = np.percentile(frame_db, NOISE_PERCENTILE)
    threshold = noise_floor + THRESHOLD_MARGIN_DB

    # True means speech
    speech_flags = frame_db >= threshold

    regions: List[Tuple[int, int]] = []
    in_speech = False
    start_frame = 0

    for idx, is_speech in enumerate(speech_flags):
        if is_speech and not in_speech:
            # silence -> speech
            in_speech = True
            start_frame = idx
        elif not is_speech and in_speech:
            # speech -> silence
            in_speech = False
            end_frame = idx

            start_ms = start_frame * hop_ms
            end_ms = end_frame * hop_ms + frame_ms
            if end_ms > total_ms:
                end_ms = total_ms

            if end_ms - start_ms >= MIN_SPEECH_MS:
                regions.append((start_ms, end_ms))

    # If speech continues to the end
    if in_speech:
        start_ms = start_frame * hop_ms
        end_ms = total_ms
        if end_ms - start_ms >= MIN_SPEECH_MS:
            regions.append((start_ms, end_ms))

    if not regions:
        return []

    # Merge segments split by short gaps
    merged: List[Tuple[int, int]] = []
    cur_start, cur_end = regions[0]

    for s, e in regions[1:]:
        if s - cur_end <= GAP_MERGE_MS:
            # Merge when the gap is short
            cur_end = e
        else:
            merged.append((cur_start, cur_end))
            cur_start, cur_end = s, e

    merged.append((cur_start, cur_end))

    # Drop segments shorter than MIN_SPEECH_MS
    merged = [
        (s, e) for (s, e) in merged
        if (e - s) >= MIN_SPEECH_MS
    ]

    return merged


def remove_silence_and_save(
    input_path: str,
    output_path: str,
    logger=None,
) -> Tuple[float, float]:
    """
    Remove low-volume noise with a custom VAD and save an MP3 that
    concatenates speech-like segments to output_path.

    Returns:
        (speech_len_seconds, original_len_seconds)
    """
    global _processed_count

    if not os.path.exists(input_path):
        _log(f"[VAD] Input not found: {input_path}", logger)
        return 0.0, 0.0

    try:
        seg = AudioSegment.from_file(input_path)
    except Exception as e:
        msg = str(e).splitlines()[0] if str(e) else repr(e)
        _log(f"[VAD] Failed to read audio ({input_path}): {msg}", logger)
        return 0.0, 0.0

    total_ms = len(seg)
    original_len = total_ms / 1000.0

    # Convert to waveform
    try:
        mono_seg, waveform, sr = _audiosegment_to_mono_np(seg)
    except Exception as e:
        _log(f"[VAD] Convert error: {e}", logger)
        return 0.0, original_len

    # Compute per-frame dB
    frame_db, frame_size, hop_size = _compute_frame_rms_db(
        waveform, sr, FRAME_MS, HOP_MS
    )

    if frame_db.size == 0:
        _log(f"[VAD] Not enough data for frame analysis: {input_path}", logger)
        return 0.0, original_len

    # Detect speech regions
    regions = _detect_speech_regions(
        frame_db,
        frame_ms=FRAME_MS,
        hop_ms=HOP_MS,
        total_ms=total_ms,
    )

    if not regions:
        _log(f"[VAD] No speech-like regions detected: {input_path}", logger)
        return 0.0, original_len

    # Slice detected regions and concatenate
    chunks = []
    for start_ms, end_ms in regions:
        start_ms = max(0, min(start_ms, total_ms))
        end_ms = max(0, min(end_ms, total_ms))
        if end_ms > start_ms:
            chunks.append(mono_seg[start_ms:end_ms])

    if not chunks:
        _log(f"[VAD] No valid chunks after slicing: {input_path}", logger)
        return 0.0, original_len

    out_seg = chunks[0]
    for c in chunks[1:]:
        out_seg += c

    if len(out_seg) < MIN_OUTPUT_MS:
        _log(
            f"[VAD] Output too short ({len(out_seg)/1000:.2f}s) "
            f"-> treat as noise: {input_path}",
            logger,
        )
        return 0.0, original_len

    # Save as MP3
    try:
        out_seg.export(output_path, format="mp3")
    except Exception as e:
        _log(f"[VAD] Export error: {e}", logger)
        return 0.0, original_len

    _processed_count += 1
    speech_len = len(out_seg) / 1000.0

    _log(
        f"[VAD] Completed ({_processed_count}) "
        f"orig={original_len:.1f}s, speech={speech_len:.1f}s, "
        f"segments={len(regions)}",
        logger,
    )

    return speech_len, original_len


def get_speech_duration(file_path: str, logger=None) -> float:
    """
    Utility function:
    Return total detected speech seconds without writing an output file.
    """
    if not os.path.exists(file_path):
        return 0.0

    try:
        seg = AudioSegment.from_file(file_path)
    except Exception:
        return 0.0

    total_ms = len(seg)

    try:
        mono_seg, waveform, sr = _audiosegment_to_mono_np(seg)
    except Exception:
        return 0.0

    frame_db, frame_size, hop_size = _compute_frame_rms_db(
        waveform, sr, FRAME_MS, HOP_MS
    )
    if frame_db.size == 0:
        return 0.0

    regions = _detect_speech_regions(
        frame_db,
        frame_ms=FRAME_MS,
        hop_ms=HOP_MS,
        total_ms=total_ms,
    )
    if not regions:
        return 0.0

    total_speech_ms = sum(e - s for (s, e) in regions)
    return total_speech_ms / 1000.0
