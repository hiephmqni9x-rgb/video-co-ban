"""Small, inspectable pipeline: validate decisions, cut media, map SRT, check output."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "input"
PLAN = ROOT / "plan"
RUN = ROOT / "runs" / "current"
PUBLIC = ROOT / "public"
TIME_RE = re.compile(r"^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})$")


def fail(message: str) -> None:
    raise SystemExit(message)


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path):
    if not path.is_file():
        fail(f"Thiếu {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def command(*args: str, capture: bool = False) -> str:
    result = subprocess.run(args, text=True, capture_output=capture, encoding="utf-8", errors="replace")
    if result.returncode:
        fail((result.stderr or result.stdout or "Lệnh thất bại")[-3000:])
    return result.stdout if capture else ""


def tool(name: str) -> str:
    override = os.environ.get(f"VIDEO_CO_BAN_{name.upper()}")
    found = override if override and Path(override).is_file() else shutil.which(name) or shutil.which(name + ".exe")
    if not found:
        fail(f"Không tìm thấy {name} trong PATH")
    return found


def probe(path: Path) -> dict:
    return json.loads(command(tool("ffprobe"), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path), capture=True))


def ms(value: str) -> int:
    match = TIME_RE.fullmatch(value.strip())
    if not match:
        fail(f"Mốc SRT sai: {value}")
    h, m, s, milli = map(int, match.groups())
    if m >= 60 or s >= 60:
        fail(f"Mốc SRT sai: {value}")
    return ((h * 60 + m) * 60 + s) * 1000 + milli


def parse_srt(path: Path) -> list[dict]:
    content = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").strip()
    cues = []
    for block in re.split(r"\n\s*\n", content):
        lines = block.splitlines()
        if len(lines) < 3 or not lines[0].strip().isdigit() or "-->" not in lines[1]:
            fail(f"Khối SRT sai: {block[:80]}")
        start, end = [ms(part) for part in lines[1].split("-->", 1)]
        cue = {"id": int(lines[0]), "start_ms": start, "end_ms": end, "text": " ".join(x.strip() for x in lines[2:] if x.strip())}
        if start >= end or not cue["text"]:
            fail(f"Cue {cue['id']} không hợp lệ")
        if cues and (cue["id"] <= cues[-1]["id"] or start < cues[-1]["end_ms"]):
            fail(f"Cue {cue['id']} trùng/chồng hoặc sai thứ tự")
        cues.append(cue)
    if not cues:
        fail("SRT trống")
    return cues


def source() -> tuple[Path, Path, list[dict], dict]:
    videos = [p for p in INPUT.iterdir() if p.suffix.lower() in {".mp4", ".mov", ".mkv"}]
    if len(videos) != 1:
        fail("input/ cần đúng một video")
    video = videos[0]
    srt = video.with_suffix(".srt")
    if not srt.is_file():
        fail(f"Thiếu SRT cùng tên: {srt.name}")
    cues = parse_srt(srt)
    info = probe(video)
    streams = info.get("streams", [])
    if not any(s.get("codec_type") == "video" for s in streams) or not any(s.get("codec_type") == "audio" for s in streams):
        fail("Video cần có cả hình và tiếng")
    duration = float(info["format"]["duration"])
    if cues[-1]["end_ms"] > duration * 1000 + 100:
        fail("SRT vượt thời lượng video")
    return video, srt, cues, info


def init() -> None:
    video, srt, cues, info = source()
    PLAN.mkdir(exist_ok=True)
    cut = PLAN / "cut.json"
    subs = PLAN / "subtitles.json"
    if not cut.exists():
        write_json(cut, [{"start_cue": cues[0]["id"], "end_cue": cues[-1]["id"], "decision": "KEEP", "reason": "Bản đầu: giữ toàn bộ để học viên xem và sửa"}])
    if not subs.exists():
        write_json(subs, [{"cue": cue["id"], "text": cue["text"]} for cue in cues])
    write_json(RUN / "ingest.json", {"video": video.name, "srt": srt.name, "duration_seconds": float(info["format"]["duration"]), "cue_count": len(cues), "status": "PASS"})
    print("Đã kiểm tra đầu vào và tạo kế hoạch ban đầu trong plan/.")


def validate_cut(rows: list, cues: list[dict]) -> list[dict]:
    if not isinstance(rows, list) or not rows:
        fail("cut.json cần danh sách quyết định")
    ids = [cue["id"] for cue in cues]
    positions = {cue_id: index for index, cue_id in enumerate(ids)}
    covered = []
    kept = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"start_cue", "end_cue", "decision", "reason"}:
            fail("Mỗi mục cut.json cần start_cue, end_cue, decision, reason")
        a, b = row["start_cue"], row["end_cue"]
        if a not in positions or b not in positions or positions[a] > positions[b]:
            fail(f"Khoảng cue sai: {a}–{b}")
        if row["decision"] not in {"KEEP", "DELETE"} or not str(row["reason"]).strip():
            fail(f"Quyết định hoặc lý do sai: {a}–{b}")
        span = ids[positions[a]:positions[b] + 1]
        covered.extend(span)
        if row["decision"] == "KEEP":
            kept.extend(span)
    if covered != ids or not kept:
        fail("Pass 1 phải phủ mọi cue đúng một lần, đúng thứ tự và KEEP ít nhất một cue")
    return [cue for cue in cues if cue["id"] in set(kept)]


def lock() -> None:
    video, srt, cues, _ = source()
    rows = read_json(PLAN / "cut.json")
    kept = validate_cut(rows, cues)
    write_json(RUN / "cut.lock.json", {"video": video.name, "video_sha256": digest(video), "srt_sha256": digest(srt), "cut_sha256": digest(PLAN / "cut.json"), "rows": rows, "kept_cues": [cue["id"] for cue in kept]})
    print(f"Đã khóa Pass 1: giữ {len(kept)}/{len(cues)} cue.")


def locked_source() -> tuple[Path, list[dict], dict, dict]:
    video, srt, cues, info = source()
    locked = read_json(RUN / "cut.lock.json")
    if locked["video"] != video.name or locked["video_sha256"] != digest(video) or locked["srt_sha256"] != digest(srt) or locked["cut_sha256"] != digest(PLAN / "cut.json"):
        fail("Nguồn hoặc Pass 1 đã đổi. Chạy python editor.py lock lại")
    validate_cut(locked["rows"], cues)
    return video, cues, info, locked


def segments(cues: list[dict], kept_ids: list[int], duration_ms: int) -> list[dict]:
    keep = set(kept_ids)
    groups = []
    current = []
    for cue in cues:
        if cue["id"] in keep:
            current.append(cue)
        elif current:
            groups.append(current)
            current = []
    if current:
        groups.append(current)
    result = []
    cursor = 0
    for index, group in enumerate(groups):
        start = 0 if group[0]["id"] == cues[0]["id"] else group[0]["start_ms"]
        end = duration_ms if group[-1]["id"] == cues[-1]["id"] else group[-1]["end_ms"]
        result.append({"source_start_ms": start, "source_end_ms": end, "output_start_ms": cursor})
        cursor += end - start
    return result


def prepare() -> None:
    video, cues, info, locked = locked_source()
    kept = set(locked["kept_cues"])
    subtitles = read_json(PLAN / "subtitles.json")
    by_id = {cue["id"]: cue for cue in cues}
    if not isinstance(subtitles, list):
        fail("subtitles.json phải là danh sách")
    seen = set()
    for item in subtitles:
        if not isinstance(item, dict) or set(item) != {"cue", "text"}:
            fail("Mỗi phụ đề cần cue và text")
        cue_id = item["cue"]
        if cue_id not in kept or cue_id in seen:
            fail(f"Pass 2 tham chiếu cue bị DELETE, không tồn tại hoặc trùng: {cue_id}")
        seen.add(cue_id)
        if not isinstance(item["text"], str) or not item["text"].strip() or len(item["text"].splitlines()) > 2:
            fail(f"Phụ đề cue {cue_id} phải có chữ và tối đa hai dòng")
    duration_ms = round(float(info["format"]["duration"]) * 1000)
    spans = segments(cues, locked["kept_cues"], duration_ms)
    total_ms = spans[-1]["output_start_ms"] + spans[-1]["source_end_ms"] - spans[-1]["source_start_ms"]
    filters = []
    for index, span in enumerate(spans):
        a = span["source_start_ms"] / 1000
        b = span["source_end_ms"] / 1000
        filters.append(f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=PTS-STARTPTS[v{index}]")
        filters.append(f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS[a{index}]")
    pairs = "".join(f"[v{i}][a{i}]" for i in range(len(spans)))
    filters.append(f"{pairs}concat=n={len(spans)}:v=1:a=1[cv][ca]")
    filters.append("[cv]fps=30,format=yuv420p[vout]")
    filters.append("[ca]aresample=48000[aout]")
    RUN.mkdir(parents=True, exist_ok=True)
    clean = RUN / "clean.mp4"
    command(tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(video), "-filter_complex", ";".join(filters), "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(clean))
    video_stream = next(s for s in info["streams"] if s["codec_type"] == "video")
    timeline = {"width": video_stream["width"], "height": video_stream["height"], "fps": 30, "durationInFrames": round(total_ms * 30 / 1000), "subtitles": []}
    for item in subtitles:
        cue = by_id[item["cue"]]
        span = next(s for s in spans if s["source_start_ms"] <= cue["start_ms"] and cue["end_ms"] <= s["source_end_ms"])
        start = span["output_start_ms"] + cue["start_ms"] - span["source_start_ms"]
        end = span["output_start_ms"] + cue["end_ms"] - span["source_start_ms"]
        timeline["subtitles"].append({"startFrame": round(start * 30 / 1000), "endFrame": round(end * 30 / 1000), "text": item["text"].strip()})
    timeline["subtitles"].sort(key=lambda x: x["startFrame"])
    PUBLIC.mkdir(exist_ok=True)
    shutil.copy2(clean, PUBLIC / "clean.mp4")
    write_json(PUBLIC / "timeline.json", timeline)
    write_json(RUN / "resolve.json", {"segments": spans, "expected_duration_ms": total_ms, "subtitle_count": len(timeline["subtitles"]), "status": "PASS"})
    print(f"Đã tạo clean.mp4 ({total_ms / 1000:.2f}s) và timeline cho Remotion.")


def qa() -> None:
    final = RUN / "final.mp4"
    if not final.is_file():
        fail("Thiếu runs/current/final.mp4; chạy npm run render")
    expected = read_json(RUN / "resolve.json")["expected_duration_ms"] / 1000
    info = probe(final)
    streams = info["streams"]
    duration = float(info["format"]["duration"])
    checks = {"video": any(s.get("codec_type") == "video" for s in streams), "audio": any(s.get("codec_type") == "audio" for s in streams), "duration": abs(duration - expected) <= 0.25}
    decode = subprocess.run([tool("ffmpeg"), "-v", "error", "-i", str(final), "-f", "null", "-"], capture_output=True, text=True)
    checks["full_decode"] = decode.returncode == 0
    report = {"status": "PASS" if all(checks.values()) else "NEEDS_REVIEW", "checks": checks, "expected_seconds": expected, "actual_seconds": duration, "decode_error": decode.stderr[-1000:]}
    write_json(RUN / "qa.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "PASS":
        fail("QA chưa đạt; xem runs/current/qa.json")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Video cơ bản: ingest, khóa cắt, render sạch và QA")
    parser.add_argument("step", choices=["init", "lock", "prepare", "qa"])
    step = parser.parse_args().step
    {"init": init, "lock": lock, "prepare": prepare, "qa": qa}[step]()

