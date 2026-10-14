# Novel Translate

Chuẩn bị dự án dịch novel với backend và SQLite chạy local; Colab hỗ trợ chạy
batch dịch qua file và có thể ngắt rồi tiếp tục từ chunk đã lưu.

Repo hiện **chỉ có tài liệu và cấu hình mẫu**, chưa có ứng dụng hoặc pipeline chạy được.

Thứ tự đọc để hiểu dự án: tổng quan → hợp đồng kỹ thuật → lộ trình.

- [Tổng quan và bối cảnh](docs/PROJECT_KNOWLEDGE.md)
- [Kế hoạch và hợp đồng dữ liệu](docs/PLAN.md)
- [Lộ trình thực hiện](docs/ROADMAP.md)
- [Cách làm việc và cài cấu hình Codex](docs/WORKFLOW.md)
- [Quy tắc agent của repo](AGENTS.md)

Bước tiếp theo là P0 trong roadmap: chuẩn bị benchmark chất lượng, tốc độ và chi phí;
chốt dữ liệu mẫu hợp lệ, budget và model trước khi chạy benchmark.
Không đưa novel thật hoặc secret vào repo.

Prompt bắt đầu gợi ý: “Đọc AGENTS.md và chuẩn bị benchmark P0 theo
docs/ROADMAP.md; xác định dữ liệu mẫu, budget và model còn thiếu trước
khi chạy. Main chốt phạm vi và giao worker phần chuẩn bị cần thiết.”
