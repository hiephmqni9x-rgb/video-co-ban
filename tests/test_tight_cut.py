"""Kiểm tra cắt khoảng lặng. Chạy: python -m unittest discover -s tests -v"""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import editor  # noqa: E402


def cue(cue_id, start, end):
    return {"id": cue_id, "start_ms": start, "end_ms": end, "text": f"cue {cue_id}"}


class PauseCutsLogic(unittest.TestCase):
    """Phần logic thuần, không cần ffmpeg."""

    def test_short_gap_is_not_cut(self):
        group = [cue(1, 0, 1000), cue(2, 1200, 2000)]  # nghỉ 200 ms < 250 ms
        self.assertEqual(editor.pause_cuts(group, 0, 2000, [(1000, 1200)]), [])

    def test_long_pause_keeps_40ms_each_side(self):
        group = [cue(1, 0, 1000), cue(2, 1800, 2800)]
        cuts = editor.pause_cuts(group, 0, 2800, [(1000, 1800)])
        self.assertEqual(cuts, [(1040, 1760, 1, 2)])  # còn lại 40 + 40 = 80 ms nghỉ

    def test_silence_shorter_than_230ms_is_ignored(self):
        group = [cue(1, 0, 1000), cue(2, 1400, 2400)]  # nghỉ 400 ms nhưng lặng thật chỉ 220 ms
        self.assertEqual(editor.pause_cuts(group, 0, 2400, [(1100, 1320)]), [])

    def test_picks_longest_silence(self):
        group = [cue(1, 0, 1000), cue(2, 2000, 3000)]
        silences = [(1000, 1300), (1400, 1950)]
        cuts = editor.pause_cuts(group, 0, 3000, silences)
        self.assertEqual(cuts, [(1440, 1910, 1, 2)])

    def test_never_cuts_into_speech(self):
        # Khoảng lặng báo lấn vào lời: phần bỏ phải nằm gọn giữa hai cue
        group = [cue(1, 0, 1000), cue(2, 1800, 2800)]
        for a, b, _, _ in editor.pause_cuts(group, 0, 2800, [(900, 1900)]):
            self.assertGreaterEqual(a, 1000)
            self.assertLessEqual(b, 1800)

    def test_cut_shorter_than_150ms_is_dropped(self):
        group = [cue(1, 0, 1000), cue(2, 1260, 2000)]  # nghỉ 260, lặng 260 -> sau trừ 80 còn 180: được cắt
        self.assertEqual(len(editor.pause_cuts(group, 0, 2000, [(1000, 1260)])), 1)
        group = [cue(1, 0, 1000), cue(2, 1250, 2000)]  # lặng 250 - 80 = 170 vẫn được; nhưng lặng 230 - 80 = 150 là ngưỡng
        self.assertEqual(len(editor.pause_cuts(group, 0, 2000, [(1010, 1240)])), 1)
        self.assertEqual(editor.pause_cuts(group, 0, 2000, [(1010, 1239)]), [])

    def test_segments_without_silences_equals_old_behaviour(self):
        cues = [cue(1, 0, 1000), cue(2, 1800, 2800), cue(3, 3000, 4000)]
        spans, removed = editor.segments(cues, [1, 3], 4000)
        self.assertEqual(removed, [])
        self.assertEqual([(s["source_start_ms"], s["source_end_ms"], s["output_start_ms"]) for s in spans],
                         [(0, 1000, 0), (3000, 4000, 1000)])

    def test_segments_split_and_output_offsets(self):
        cues = [cue(1, 0, 1000), cue(2, 1800, 2800), cue(3, 3000, 4000)]
        spans, removed = editor.segments(cues, [1, 2, 3], 4000, [(1000, 1800)])
        self.assertEqual([(s["source_start_ms"], s["source_end_ms"], s["output_start_ms"]) for s in spans],
                         [(0, 1040, 0), (1760, 4000, 1040)])
        self.assertEqual(removed, [{"start_ms": 1040, "end_ms": 1760, "between_cues": [1, 2]}])

    def test_junctions_record_80_for_pause_and_60_for_join(self):
        cues = [cue(1, 0, 1000), cue(2, 1800, 2800), cue(3, 3600, 4600), cue(4, 4800, 5800)]
        by_id = {c["id"]: c for c in cues}
        # cue 3 bị DELETE: đoạn KEEP thứ nhất gồm cue 1-2 (có nghỉ bị cắt), đoạn thứ hai là cue 4
        spans, removed = editor.segments(cues, [1, 2, 4], 5800, [(1000, 1800)])
        result = editor.junctions(spans, removed, by_id)
        self.assertEqual([j["type"] for j in result], ["tightened_source_pause", "semantic_join"])
        self.assertEqual([j["target_gap_ms"] for j in result], [80, 60])
        self.assertEqual(result[0]["actual_gap_ms"], 80)   # 800 - 720 bị cắt
        self.assertEqual(result[1]["actual_gap_ms"], 0)    # nối sát mép cue
        self.assertEqual(result[0]["source_gap_removed_ms"], 720)

    def test_pause_not_cut_across_deleted_cue(self):
        # Cue 2 bị DELETE: hai đoạn KEEP khác nhau, luật cắt lặng chỉ chạy bên trong từng đoạn
        cues = [cue(1, 0, 1000), cue(2, 1800, 2800), cue(3, 3600, 4600)]
        spans, removed = editor.segments(cues, [1, 3], 4600, [(1000, 1800), (2800, 3600)])
        self.assertEqual(removed, [])
        self.assertEqual(len(spans), 2)


def ffmpeg_available():
    try:
        editor.tool("ffmpeg")
        editor.tool("ffprobe")
        return True
    except SystemExit:
        return False


@unittest.skipUnless(ffmpeg_available(), "Không có ffmpeg/ffprobe trong PATH")
class EndToEnd(unittest.TestCase):
    """Video tổng hợp: tiếng 1 s, lặng 0,8 s, tiếng 1 s, lặng 0,2 s, tiếng 1 s."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="vcb-test-"))
        cls.saved = (editor.INPUT, editor.PLAN, editor.RUN, editor.PUBLIC)
        editor.INPUT, editor.PLAN, editor.RUN, editor.PUBLIC = (
            cls.tmp / "input", cls.tmp / "plan", cls.tmp / "runs" / "current", cls.tmp / "public")
        editor.INPUT.mkdir(parents=True)
        editor.RUN.mkdir(parents=True)
        cls.video = editor.INPUT / "test.mp4"
        tone = "sine=frequency=440:sample_rate=48000:duration=1"
        silence = "anullsrc=r=48000:cl=mono:d={}"
        subprocess.run([
            editor.tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=320x568:r=30:d=4",
            "-f", "lavfi", "-i", tone, "-f", "lavfi", "-i", silence.format("0.8"),
            "-f", "lavfi", "-i", tone, "-f", "lavfi", "-i", silence.format("0.2"),
            "-f", "lavfi", "-i", tone,
            "-filter_complex", "[1:a][2:a][3:a][4:a][5:a]concat=n=5:v=0:a=1[a]",
            "-map", "0:v", "-map", "[a]", "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", str(cls.video)], check=True)

    @classmethod
    def tearDownClass(cls):
        editor.INPUT, editor.PLAN, editor.RUN, editor.PUBLIC = cls.saved
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_detect_silences_finds_the_real_pauses(self):
        silences = editor.detect_silences(self.video)
        long_ones = [s for s in silences if s[1] - s[0] >= 600]
        self.assertEqual(len(long_ones), 1)
        self.assertAlmostEqual(long_ones[0][0], 1000, delta=60)
        self.assertAlmostEqual(long_ones[0][1], 1800, delta=60)

    def test_prepare_cuts_only_the_long_pause(self):
        (editor.RUN / "corrected.srt").write_text(
            "1\n00:00:00,000 --> 00:00:01,000\ncue 1\n\n2\n00:00:01,800 --> 00:00:02,800\ncue 2\n\n"
            "3\n00:00:03,000 --> 00:00:04,000\ncue 3\n", encoding="utf-8")
        editor.write_json(editor.RUN / "proposals.json", {
            "video": self.video.name, "video_sha256": editor.digest(self.video),
            "srt_sha256": editor.digest(editor.RUN / "corrected.srt"), "cuts": []})
        editor.review(None, True)  # người dùng giữ hết
        editor.prepare()
        resolve = json.loads((editor.RUN / "resolve.json").read_text(encoding="utf-8"))
        self.assertEqual(len(resolve["removed_pauses"]), 1)  # nghỉ 0,2 s không bị đụng tới
        removed = resolve["removed_pauses"][0]
        self.assertAlmostEqual(removed["start_ms"], 1040, delta=60)
        self.assertAlmostEqual(removed["end_ms"] - removed["start_ms"], 720, delta=100)
        info = editor.probe(editor.RUN / "clean.mp4")
        self.assertAlmostEqual(float(info["format"]["duration"]) * 1000, resolve["expected_duration_ms"], delta=120)
        timeline = json.loads((editor.PUBLIC / "timeline.json").read_text(encoding="utf-8"))
        # Phụ đề cue 2 phải dời đúng theo đoạn đã cắt, không lệch theo mốc gốc
        cue2 = timeline["subtitles"][1]
        expected_start_ms = resolve["segments"][1]["output_start_ms"] + 1800 - resolve["segments"][1]["source_start_ms"]
        self.assertAlmostEqual(cue2["startFrame"], round(expected_start_ms * 30 / 1000), delta=1)


if __name__ == "__main__":
    unittest.main()
