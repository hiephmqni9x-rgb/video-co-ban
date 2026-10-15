# video-co-ban

Repo mẫu để học dựng video nói chuyện: **chọn phần giữ lại → cắt video → phụ đề trắng → xuất và kiểm tra**. FFmpeg xử lý hình/tiếng; Remotion làm tầng trình bày để bạn tự thêm hiệu ứng sau này. Bản mẫu chưa có zoom, icon, nhạc nền, stock clip hay hiệu ứng chữ.

## Cài đặt

- Python 3.10+, Node.js 20+, FFmpeg và ffprobe trong `PATH`.
- Chạy `npm install` tại thư mục repo. Các phiên bản Remotion được cố định trong `package.json`.

Nếu FFmpeg không nằm trong `PATH`, đặt biến môi trường `VIDEO_CO_BAN_FFMPEG` và `VIDEO_CO_BAN_FFPROBE` trỏ đến hai file thực thi tương ứng.

## Đầu vào

Đặt đúng **một video** (`.mp4`, `.mov` hoặc `.mkv`) và **một SRT cùng tên gốc** vào `input/`, ví dụ `input/bai-noi.mp4` và `input/bai-noi.srt`. File nguồn không bị sửa. Bản đầu yêu cầu video có cả hình và tiếng, SRT đã có mốc thời gian.

## Dòng chảy

```text
01 ingest → 02 Pass 1 KEEP/DELETE → khóa kế hoạch cắt
          → 02 Pass 2 chia phụ đề trên phần KEEP
          → 03 resolve mốc thời gian → 04 FFmpeg clean.mp4
          → 05 Remotion final.mp4 → 06 QA
```

Hai pass là **hai quyết định biên tập của bạn hoặc Codex**, được lưu thành hai file JSON để xem và sửa. Chúng không tự gọi AI khi chạy lệnh. Quy tắc trong `prompts/` giúp Codex tạo từng file; chương trình kiểm tra hợp lệ trước khi render. Pass 2 không thể đổi KEEP/DELETE.

### 1. Kiểm tra và tạo bản kế hoạch ban đầu

```powershell
python editor.py init
```

Lệnh tạo `plan/cut.json` (mặc định KEEP toàn bộ) và `plan/subtitles.json` (mặc định lấy nguyên văn từng cue SRT). Đây là dữ liệu khởi đầu **để chỉnh**, không phải kết quả AI đã biên tập. Nó cũng ghi báo cáo đầu vào vào `runs/current/ingest.json`.

### 2. Pass 1: quyết định cắt

Dùng [prompts/pass1.md](prompts/pass1.md) với Codex, hoặc tự sửa `plan/cut.json`. Mỗi dòng là một nhóm cue liên tiếp, có `decision` là `KEEP` hoặc `DELETE` và `reason`. Mọi cue phải được phủ đúng một lần. Sau khi xem và chốt:

```powershell
python editor.py lock
```

Lệnh lưu bản khóa ở `runs/current/cut.lock.json`. Sửa `plan/cut.json` sau đó thì phải chạy `lock` lại; khi đó cũng cần xem lại Pass 2.

### 3. Pass 2: phụ đề trắng

Dùng [prompts/pass2.md](prompts/pass2.md) với Codex, hoặc sửa `plan/subtitles.json`. Mỗi mục tham chiếu một cue được KEEP và có một `text` tối đa hai dòng. Không thêm lời không có trong tiếng nói. Có thể bỏ một cue khỏi danh sách nếu cố ý không hiện chữ. `python editor.py prepare` sẽ báo lỗi nếu Pass 2 tham chiếu cue đã DELETE.

### 4. Render và kiểm tra

```powershell
python editor.py prepare
npm run render
python editor.py qa
```

`prepare` tạo `runs/current/clean.mp4`, `public/clean.mp4` và `public/timeline.json`. Remotion đọc hai file trong `public/` để tạo `runs/current/final.mp4`. `qa` kiểm tra file cuối bằng ffprobe và giải mã toàn bộ bằng FFmpeg; kết quả ở `runs/current/qa.json`. Hãy xem/nghe video cuối để xác nhận điểm cắt và lời phụ đề.

Muốn xem hoặc sửa phần trình bày trong Remotion: `npm run studio`. Sau khi đổi phụ đề, chạy lại `prepare`, `npm run render`, `qa`. Sau khi đổi kế hoạch cắt, chạy lại từ `lock`.

## Cấu trúc

- `editor.py`: ingest, kiểm tra kế hoạch, khóa, ánh xạ thời gian, FFmpeg và QA.
- `plan/`: hai quyết định của Pass 1 và Pass 2.
- `src/`: component Remotion. Bắt đầu mở rộng hiệu ứng tại đây.
- `input/`: file gốc, không đưa lên Git.
- `runs/`, `public/`: file tạo ra khi chạy, không đưa lên Git.

`clean.mp4` giữ tỷ lệ và kích thước nguồn. Dùng SRT đúng tiếng nói; bản mẫu không tự phiên âm hoặc tự sửa lỗi nhận dạng lời nói.


