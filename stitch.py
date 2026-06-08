#!/usr/bin/env python3
"""
Adobe Connect Local Stitcher
Merges local FLV + XML files from Adobe Connect sessions with proper timing.
"""

import subprocess
import json
import os
import sys
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

# ========== CONFIGURATION ==========
OUTPUT_VIDEO = "output.mp4"
USE_CUDA = True           # Set to False for CPU encoding if nvenc fails
CRF = 18                  # Quality (lower=better, 18-23 good)
FPS = 30
CANVAS_W = 1280
CANVAS_H = 720
PADDING_MS = 2000
# ===================================

def find_tool(name):
    """Find ffmpeg/ffprobe in PATH or current directory"""
    for ext in ["", ".exe"]:
        p = Path(name + ext)
        if p.is_file():
            return str(p)
    return shutil.which(name) or name

def get_base_tick(xml_path):
    """Extract pacingTick offset from XML file"""
    try:
        tree = ET.parse(str(xml_path))
        root = tree.getroot()
        earliest_time = float('inf')
        best_base = None

        for elem in root.findall(".//Message"):
            method = elem.find("Method")
            if method is None or not method.text or "pacingTick" not in method.text:
                continue
            time_str = elem.get("time")
            num = elem.find("Number")
            if time_str is None or num is None or num.text is None:
                continue
            try:
                offset = int(time_str.strip())
                tick = int(num.text.strip())
                if offset < earliest_time and offset >= 0:
                    earliest_time = offset
                    best_base = tick - offset
            except ValueError:
                continue
        return best_base
    except Exception as e:
        print(f"Error parsing {xml_path}: {e}")
        return None

def probe_duration(ffprobe, filepath):
    """Get duration in seconds using ffprobe"""
    try:
        result = subprocess.run(
            [ffprobe, "-v", "quiet", "-show_format", "-show_streams", "-print_format", "json", str(filepath)],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            info = json.loads(result.stdout)
            # Try to grab format duration first
            if "format" in info and "duration" in info["format"]:
                return float(info["format"]["duration"])
            # Fallback to stream duration if format is missing (common in unfinished FLVs)
            for s in info.get("streams", []):
                if "duration" in s:
                    return float(s["duration"])
    except:
        pass
    return 0.0

def has_stream(ffprobe, filepath, stream_type):
    """Check if file has video or audio stream"""
    try:
        result = subprocess.run(
            [ffprobe, "-v", "quiet", "-show_streams", "-print_format", "json", str(filepath)],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            info = json.loads(result.stdout)
            return any(s.get("codec_type") == stream_type for s in info.get("streams", []))
    except:
        pass
    return False

def collect_media(ffprobe, folder):
    """Find all FLV files and extract timing from XMLs"""
    xml_files = list(folder.glob("*.xml"))
    xml_bases = {}

    for xp in xml_files:
        base = get_base_tick(xp)
        if base is not None:
            xml_bases[xp.stem] = base

    if not xml_bases:
        print("No pacingTick found in XML files")
        return [], []

    global_base = min(xml_bases.values())
    print(f"Global base tick: {global_base}")

    screen_clips = []
    audio_clips = []

    for flv in sorted(folder.glob("*.flv")):
        stem = flv.stem
        if stem not in xml_bases:
            print(f"Skipping {flv.name} (no pacingTick found)")
            continue

        has_v = has_stream(ffprobe, flv, "video")
        has_a = has_stream(ffprobe, flv, "audio")
        if not has_v and not has_a:
            continue

        dur = probe_duration(ffprobe, flv)
        if dur <= 0:
            print(f"Skipping {flv.name} (duration 0 or unreadable)")
            continue

        start_ms = max(0.0, xml_bases[stem] - global_base)
        end_ms = start_ms + (dur * 1000)

        entry = {"file": flv, "start_ms": start_ms, "end_ms": end_ms}

        if has_v and "screenshare" in flv.name.lower():
            screen_clips.append(entry)
        if has_a:
            audio_clips.append(entry)

        print(f"  {flv.name}: {start_ms/1000:.1f}s -> {end_ms/1000:.1f}s")

    return screen_clips, audio_clips

def render_video(ffmpeg, folder, screen_clips, audio_clips, total_ms, output_path):
    """Render final MP4 directly using FFmpeg filter complex"""
    total_sec = total_ms / 1000.0
    cmd = [ffmpeg, "-y"]

    # Input 0: Black canvas background mapping the full duration
    cmd += ["-f", "lavfi", "-i", f"color=c=black:s={CANVAS_W}x{CANVAS_H}:r={FPS}:d={total_sec}"]

    video_count = len(screen_clips)
    audio_count = len(audio_clips)

    # Supply videos to FFmpeg
    for c in screen_clips:
        cmd += ["-i", str(c["file"])]

    # Supply audios to FFmpeg
    for c in audio_clips:
        cmd += ["-i", str(c["file"])]

    # Supply a silent audio track acting as a base
    cmd += ["-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate=44100:duration={total_sec}"]
    silence_idx = 1 + video_count + audio_count

    filters = []

    # -- VIDEO PROCESSING --
    if video_count > 0:
        for idx, c in enumerate(screen_clips):
            offset_sec = c["start_ms"] / 1000.0
            # Scale video into aspect ratio padding box, then shift its timestamp to offset_sec
            filters.append(
                f"[{1+idx}:v]scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=decrease,"
                f"pad={CANVAS_W}:{CANVAS_H}:(ow-iw)/2:(oh-ih)/2,"
                f"format=yuv420p,setpts=PTS-STARTPTS+{offset_sec}/TB[v{idx}]"
            )

        # Progressively overlay videos on the black canvas
        prev = "[0:v]"
        for idx, c in enumerate(screen_clips):
            offset_sec = c["start_ms"] / 1000.0
            end_sec = c["end_ms"] / 1000.0
            out_node = f"[vo{idx}]" if idx < video_count - 1 else "[vout]"

            # 'enable' triggers rendering only during the active offset.
            # 'eof_action=pass' prevents the last frame from getting stuck after EOF.
            filters.append(
                f"{prev}[v{idx}]overlay=0:0:enable='between(t,{offset_sec},{end_sec})':eof_action=pass{out_node}"
            )
            prev = out_node
    else:
        filters.append("[0:v]copy[vout]")

    # -- AUDIO PROCESSING --
    audio_inputs = []
    if audio_count > 0:
        for idx, c in enumerate(audio_clips):
            offset_ms = int(c["start_ms"])
            # Delay left and right tracks by their start offset in milliseconds
            filters.append(f"[{1+video_count+idx}:a]adelay={offset_ms}|{offset_ms}[a{idx}]")
            audio_inputs.append(f"[a{idx}]")

    audio_inputs.append(f"[{silence_idx}:a]")

    if len(audio_inputs) > 1:
        # mix all delayed audio streams. normalize=0 avoids dropping volume when multiple speakers talk
        inputs_str = "".join(audio_inputs)
        filters.append(f"{inputs_str}amix=inputs={len(audio_inputs)}:duration=longest:normalize=0[outa]")
    else:
        filters.append(f"[{silence_idx}:a]copy[outa]")

    cmd += ["-filter_complex", ";".join(filters)]
    cmd += ["-map", "[vout]", "-map", "[outa]"]

    # -- ENCODING SETTINGS --
    if USE_CUDA:
        vcodec = "h264_nvenc"
        vopts = ["-preset", "p7", "-rc", "vbr", "-cq", str(CRF), "-b:v", "0"]
    else:
        vcodec = "libx264"
        vopts = ["-preset", "medium", "-crf", str(CRF)]

    cmd += ["-c:v", vcodec] + vopts
    cmd += ["-c:a", "aac", "-b:a", "128k"]
    cmd += ["-movflags", "+faststart", str(output_path)]

    print(f"\nConstructing FFmpeg command (CUDA={'ON' if USE_CUDA else 'OFF'})...")
    
    # Real-time console streaming for debugging long encodes
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for line in process.stdout:
        sys.stdout.write(line)

    process.wait()

    if process.returncode != 0:
        print("\nFFmpeg error during rendering.")
        return False
    return True

def main():
    folder = Path.cwd()
    print(f"Working in: {folder}")

    ffmpeg = find_tool("ffmpeg")
    ffprobe = find_tool("ffprobe")

    if not ffmpeg or not ffprobe:
        print("ERROR: ffmpeg/ffprobe not found. Verify they are installed and in your PATH.")
        sys.exit(1)

    screen_clips, audio_clips = collect_media(ffprobe, folder)

    if not screen_clips and not audio_clips:
        print("No valid media files found or pacingTick missing in XMLs.")
        sys.exit(1)

    total_ms = max([c["end_ms"] for c in screen_clips + audio_clips], default=0) + PADDING_MS
    output_path = folder / OUTPUT_VIDEO
    
    print(f"Total session duration: {total_ms/1000.0:.1f}s")
    
    if render_video(ffmpeg, folder, screen_clips, audio_clips, total_ms, output_path):
        print(f"\nSuccess! Video saved to: {output_path.absolute()}")
    else:
        print("\nRendering failed. Check the FFmpeg output above.")

if __name__ == "__main__":
    main()