# Pass 1 — quyết định cắt

Đọc toàn bộ SRT trong `input/`, đối chiếu tiếng thật trong video trước khi quyết định. Sửa SRT nếu nghe thấy lỗi và ghi rõ những chỗ chưa chắc. Giữ mạch ý, cảm xúc, ví dụ và cầu nối cần thiết. Chỉ DELETE đoạn ậm ừ, nói hỏng, lặp ngay hoặc rõ ràng không phục vụ nội dung. Khi không chắc, KEEP.

Sửa `plan/cut.json`: mỗi mục có `start_cue`, `end_cue`, `decision` (`KEEP` hoặc `DELETE`) và `reason`. Các mục phải phủ mọi cue SRT đúng một lần, theo thứ tự. Không tạo mốc thời gian mới. Không quyết định kiểu chữ hay hiệu ứng trong pass này. Tóm tắt những đoạn DELETE để người dùng duyệt trước khi chạy `python editor.py lock`.


