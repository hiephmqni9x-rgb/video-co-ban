# Pass 2 — chia phụ đề

Đọc SRT và `runs/current/cut.lock.json`. Chỉ xử lý những cue được KEEP. Sửa `plan/subtitles.json`: mỗi mục gồm `cue` và `text`, tối đa hai dòng, chữ phải đúng lời người nói và không thêm ý. Dòng ngắn, dễ đọc; tránh ngắt giữa cụm nghĩa. Không thay đổi KEEP/DELETE hoặc mốc SRT gốc. Không thêm màu, hiệu ứng, icon, camera, nhạc hay visual. Nếu một cue không cần hiện chữ, có thể bỏ mục đó và ghi lý do cho người dùng.

