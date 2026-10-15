"""Automatic Vietnamese ASR and contextual editorial proposals.

AI proposes changes. This module never approves a cut or renders media.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


def _schema(name: str, properties: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "required": list(properties), "properties": properties}


CORRECTION_SCHEMA = _schema("corrections", {"items": {"type": "array", "items": _schema("item", {
    "cue": {"type": "integer"}, "text": {"type": "string"}, "uncertain_reason": {"type": "string"},
})}})

CUT_SCHEMA = _schema("cut_proposals", {"cuts": {"type": "array", "items": _schema("cut", {
    "start_cue": {"type": "integer"}, "end_cue": {"type": "integer"}, "reason": {"type": "string"},
})}})


def ask_ai(prompt: str, schema: dict, output_dir: Path, name: str) -> dict:
    """Use the Codex login in a cloud task, or an explicitly configured API key."""
    backend = os.environ.get("VIDEO_CO_BAN_AI_BACKEND", "codex").lower()
    output_dir.mkdir(parents=True, exist_ok=True)
    if backend == "codex":
        local_cli = Path(__file__).resolve().parent / "node_modules" / ".bin" / ("codex.cmd" if os.name == "nt" else "codex")
        executable = shutil.which("codex") or shutil.which("codex.cmd") or (str(local_cli) if local_cli.is_file() else None)
        if not executable:
            raise RuntimeError("Thiếu Codex CLI. Cài Codex CLI hoặc đặt VIDEO_CO_BAN_AI_BACKEND=openai và OPENAI_API_KEY")
        schema_path = output_dir / f"{name}.schema.json"
        result_path = output_dir / f"{name}.response.json"
        schema_path.write_text(json.dumps(schema, ensure_ascii=False), encoding="utf-8")
        args = [executable, "exec", "--skip-git-repo-check", "--sandbox", "read-only",
                "--output-schema", str(schema_path), "--output-last-message", str(result_path), "-"]
        model = os.environ.get("VIDEO_CO_BAN_TEXT_MODEL")
        if model:
            args[2:2] = ["--model", model]
        result = subprocess.run(args, input=prompt, text=True, capture_output=True,
                                encoding="utf-8", errors="replace", cwd=output_dir, timeout=1200)
        if result.returncode:
            raise RuntimeError(f"Codex AI lỗi: {(result.stderr or result.stdout)[-2000:]}")
        answer = json.loads(result_path.read_text(encoding="utf-8-sig"))
    elif backend == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("Thiếu OPENAI_API_KEY cho VIDEO_CO_BAN_AI_BACKEND=openai")
        from openai import OpenAI
        response = OpenAI().responses.create(
            model=os.environ.get("VIDEO_CO_BAN_TEXT_MODEL", "gpt-4o"),
            input=[{"role": "system", "content": "Bạn là biên tập viên video nói tiếng Việt. Trả về JSON đúng schema."},
                   {"role": "user", "content": prompt}],
            text={"format": {"type": "json_schema", "name": name, "strict": True, "schema": schema}},
            store=False,
        )
        answer = json.loads(response.output_text)
    else:
        raise RuntimeError("VIDEO_CO_BAN_AI_BACKEND chỉ nhận codex hoặc openai")
    if not isinstance(answer, dict):
        raise RuntimeError("AI không trả về đối tượng JSON")
    return answer


def transcribe(video: Path, output_dir: Path) -> tuple[list[dict], dict]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as error:
        raise RuntimeError("Thiếu faster-whisper. Chạy pip install -r requirements.txt") from error
    device = os.environ.get("VIDEO_CO_BAN_ASR_DEVICE", "cpu")
    model_name = os.environ.get("VIDEO_CO_BAN_ASR_MODEL", "large-v3-turbo" if device == "cuda" else "medium")
    compute_type = "float16" if device == "cuda" else "int8"
    model = WhisperModel(model_name, device=device, compute_type=compute_type)
    result, info = model.transcribe(str(video), language="vi", vad_filter=True, beam_size=5)
    cues = []
    previous_end = 0
    for segment in result:
        text = segment.text.strip()
        start = max(previous_end, round(segment.start * 1000))
        end = round(segment.end * 1000)
        if not text or end <= start:
            continue
        cues.append({"id": len(cues) + 1, "start_ms": start, "end_ms": end, "text": text})
        previous_end = end
    if not cues:
        raise RuntimeError("Không nhận ra lời nói trong video; cần kiểm tra audio")
    metadata = {"backend": "faster-whisper", "model": model_name, "device": device,
                "language": info.language, "language_probability": info.language_probability}
    return cues, metadata


def correct_context(cues: list[dict], output_dir: Path) -> tuple[list[dict], list[dict]]:
    """Correct every cue with nearby context; preserve the ASR timing."""
    corrected = []
    uncertain = []
    for offset in range(0, len(cues), 50):
        batch = cues[offset:offset + 50]
        context = cues[max(0, offset - 5):min(len(cues), offset + 55)]
        prompt = (
            "Đọc đoạn phiên âm máy và ngữ cảnh trước/sau. Sửa lỗi chính tả, dấu câu, tên riêng "
            "chỉ khi ngữ cảnh đủ rõ. Không viết lại ý, không thêm lời, không đổi mốc thời gian. "
            "Nếu từ nào không chắc, giữ nguyên và ghi uncertain_reason. "
            "Trả về đúng một item cho MỖI cue trong TARGET, theo thứ tự.\n"
            f"CONTEXT: {json.dumps(context, ensure_ascii=False)}\n"
            f"TARGET: {json.dumps(batch, ensure_ascii=False)}"
        )
        result = ask_ai(prompt, CORRECTION_SCHEMA, output_dir, f"correction_{offset // 50 + 1}")
        items = result.get("items", [])
        if [x.get("cue") for x in items] != [x["id"] for x in batch]:
            raise RuntimeError("AI sửa lời nhưng thiếu/thừa/đổi thứ tự cue")
        for original, item in zip(batch, items):
            text = item.get("text", "").strip()
            if not text:
                raise RuntimeError(f"AI trả lời rỗng ở cue {original['id']}")
            corrected.append({**original, "text": text})
            if item.get("uncertain_reason", "").strip():
                uncertain.append({"cue": original["id"], "reason": item["uncertain_reason"].strip()})
    return corrected, uncertain


def propose_cuts(cues: list[dict], output_dir: Path) -> list[dict]:
    prompt = (
        "Đọc TOÀN BỘ lời nói theo thứ tự. Chỉ đề xuất bỏ ậm ừ, lần nói hỏng, tự sửa, "
        "lặp ý ngay hoặc đoạn thừa rõ ràng. Giữ mạch lập luận, ví dụ, cảm xúc và cầu nối. "
        "Không cắt chỉ vì ASR chưa rõ hoặc vì câu dài. Khi nghi ngờ, giữ lại. "
        "Trả về CHỈ các đoạn đề xuất DELETE, theo cue liên tiếp, với lý do cụ thể. "
        "Đây là đề xuất để người dùng duyệt, chưa được phép thi hành.\n"
        f"TRANSCRIPT: {json.dumps(cues, ensure_ascii=False)}"
    )
    result = ask_ai(prompt, CUT_SCHEMA, output_dir, "cut_proposals")
    proposals = result.get("cuts", [])
    ids = [cue["id"] for cue in cues]
    positions = {cue_id: i for i, cue_id in enumerate(ids)}
    prior_end = -1
    for item in proposals:
        a, b = item.get("start_cue"), item.get("end_cue")
        if a not in positions or b not in positions or positions[a] > positions[b] or positions[a] <= prior_end:
            raise RuntimeError("AI đề xuất đoạn cắt sai, chồng nhau hoặc không theo thứ tự")
        if not str(item.get("reason", "")).strip():
            raise RuntimeError("AI đề xuất cắt nhưng thiếu lý do")
        prior_end = positions[b]
    if proposals and positions[proposals[0]["start_cue"]] == 0 and prior_end == len(cues) - 1:
        covered = sum(positions[p["end_cue"]] - positions[p["start_cue"]] + 1 for p in proposals)
        if covered == len(cues):
            raise RuntimeError("AI đề xuất xóa toàn bộ video")
    by_id = {cue["id"]: cue for cue in cues}
    return [{"id": i + 1, "start_cue": p["start_cue"], "end_cue": p["end_cue"],
             "start_ms": by_id[p["start_cue"]]["start_ms"], "end_ms": by_id[p["end_cue"]]["end_ms"],
             "text": " ".join(cue["text"] for cue in cues[positions[p["start_cue"]]:positions[p["end_cue"]] + 1]),
             "reason": p["reason"].strip()} for i, p in enumerate(proposals)]

