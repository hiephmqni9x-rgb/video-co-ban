# video-co-ban

Repo học dựng video nói chuyện từ **một video quay bằng điện thoại**. Hệ thống tự phiên âm tiếng Việt, dùng AI sửa lời theo ngữ cảnh và **đề xuất** đoạn nên cắt. Người dùng quyết định cắt đoạn nào trước khi FFmpeg hoặc Remotion chạy. Bản đầu chỉ có phụ đề trắng; không có zoom, icon, stock clip, nhạc nền hay SFX.

## Chạy trên môi trường đám mây

Mở repo bằng GitHub Codespaces hoặc một môi trường Linux có Python 3.10+, Node.js 20+ và quyền cài FFmpeg. Codespaces tự chạy `scripts/setup-cloud.sh`. Ở môi trường Linux khác, chạy:

```bash
bash scripts/setup-cloud.sh
```

Đặt **đúng một file** `.mp4`, `.mov` hoặc `.mkv` vào `input/`. Có thể tải file từ điện thoại lên workspace trong giao diện cloud đang dùng, hoặc gửi video cho tác vụ Codex và yêu cầu đặt tệp đính kèm vào `input/`. Chương trình nhận video trong thư mục này; nó không tự truy cập thư viện ảnh trên điện thoại. Video và mọi bản render được `.gitignore`, không đưa lên GitHub.

## Dòng chảy có bước duyệt

```text
1 video → phiên âm thô → AI sửa lời theo ngữ cảnh
        → AI đề xuất DELETE và lý do → NGƯỜI DÙNG DUYỆT
        → khóa KEEP/DELETE → phụ đề trắng → Resolve
        → FFmpeg clean.mp4 → Remotion final.mp4 → QA
```

### 1. Tự phiên âm và lập đề xuất

```bash
.venv/bin/python editor.py init
.venv/bin/python editor.py review
```

`init` dùng [faster-whisper](https://github.com/SYSTRAN/faster-whisper) để tạo `runs/current/raw.srt`, sau đó AI sửa theo ngữ cảnh thành `runs/current/corrected.srt` và ghi `runs/current/proposals.json`. Nếu bạn đã có SRT cùng tên trong `input/`, hệ dùng nó làm bản thô và vẫn chạy bước sửa theo ngữ cảnh. File `runs/current/proposals.json` lưu tên mô hình, các chỗ AI chưa chắc và các đề xuất cắt. `review` **chỉ báo những đoạn được đề xuất cắt**, mốc thời gian, lời và lý do. Chưa có lệnh duyệt thì hệ không render.

Mặc định bước sửa ngữ cảnh và đề xuất cắt dùng Codex CLI. Script cài đặt tải CLI; bạn cần đăng nhập bằng `node_modules/.bin/codex login` nếu môi trường chưa có phiên đăng nhập. Nếu dùng OpenAI API, đặt `VIDEO_CO_BAN_AI_BACKEND=openai` và `OPENAI_API_KEY` trong secret của môi trường; không ghi khóa vào repo. Có thể đổi model văn bản bằng `VIDEO_CO_BAN_TEXT_MODEL`. ASR mặc định dùng `medium` trên CPU hoặc `large-v3-turbo` khi đặt `VIDEO_CO_BAN_ASR_DEVICE=cuda`; đổi bằng `VIDEO_CO_BAN_ASR_MODEL`. Lần chạy đầu tải model nên cần mạng và dung lượng trống.

### 2. Người dùng quyết định

Ví dụ AI đề xuất ba đoạn `#1`, `#2`, `#3`. Muốn cắt **chỉ #1 và #3**:

```bash
.venv/bin/python editor.py review --approve 1,3
```

Muốn giữ toàn bộ:

```bash
.venv/bin/python editor.py review --keep-all
```

Lệnh duyệt ghi `runs/current/approval.json`, `plan/cut.json`, `plan/subtitles.json` và khóa Pass 1. Những đề xuất không được duyệt đều được KEEP. Thay đổi video, phiên âm, đề xuất hoặc kế hoạch cắt sẽ làm khóa hết hiệu lực; phải duyệt lại. Có thể sửa chữ trong `plan/subtitles.json` sau khi duyệt, nhưng Pass 2 không được đổi KEEP/DELETE.

### 3. Render và kiểm tra

```bash
.venv/bin/python editor.py prepare
npm run render
.venv/bin/python editor.py qa
```

`prepare` ánh xạ thời gian và dùng FFmpeg tạo `runs/current/clean.mp4`. Remotion trong `src/` đặt phụ đề trắng lên video sạch và xuất `runs/current/final.mp4`. `qa` kiểm tra hình, tiếng, thời lượng và giải mã toàn file; báo cáo nằm trong `runs/current/qa.json`. Vẫn cần xem/nghe file cuối để nhận ra lỗi nội dung hoặc điểm cắt gắt mà kiểm tra kỹ thuật không phát hiện.

## Mở rộng sau này

- `editor_ai.py`: backend phiên âm và AI. Có thể thay model ASR mà không sửa phần cắt hoặc Remotion.
- `editor.py`: ingest, quyết định duyệt, khóa, cắt, ánh xạ mốc và QA.
- `src/`: tầng trình bày Remotion; bắt đầu thêm hiệu ứng ở đây.

AI hiện sửa lời dựa trên bản phiên âm máy và ngữ cảnh các cue lân cận. Những chỗ chưa chắc được ghi trong `proposals.json` để người dùng nghe lại; không coi bản sửa tự động là bằng chứng tuyệt đối về âm thanh gốc.

