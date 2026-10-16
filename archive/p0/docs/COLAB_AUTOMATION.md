# Ghi chép lịch sử: chạy P0 Qwen3.5 qua CLI

Script này thuộc benchmark P0 đã lưu trữ; không dùng cho luồng app hiện hành.
User đã chọn Qwen3.5 làm provider tích hợp. Xem hướng dẫn batch app tại
[`docs/REAL_BATCH.md`](../../../docs/REAL_BATCH.md).

Sau khi đăng nhập `./scripts/colab` và xác nhận Google Drive trong kernel Colab
đang dùng, chạy một lệnh từ thư mục gốc:

```bash
.venv/bin/python scripts/run_p0_colab.py
```

Lệnh kiểm tra alias `qwen35-vscode`, assignment T4, notebook Qwen3.5 và trạng thái
kernel đang rảnh. Sau đó nó kiểm tra các package pin, chép source tin cậy từ
`build_notebook.py`, áp dụng đúng profile Qwen3.5 và gọi runner hiện có. Mặc định
runner xác thực checkpoint trên Drive rồi xử lý mọi chunk còn thiếu. Dùng
`--limit 1` để chạy smoke một chunk.

Lệnh không tạo, dừng hoặc cấp runtime. Nếu Drive chưa được xác thực và mount trong
kernel, lệnh dừng với hướng dẫn; Google OAuth không bị bỏ qua. Nếu thiếu hoặc sai
package pin, lệnh cài đúng phiên bản bằng Python của kernel rồi yêu cầu chạy lại
với `--restart-kernel`. Cờ này chủ động restart đúng kernel Colab hiện có trước
khi tải model; checkpoint và file trên Drive vẫn được giữ.

`--dry-run` chỉ in model, revision, corpus path, alias và limit; không kết nối.
Script không lưu output remote hoặc văn bản novel vào máy local. Kiểm tra offline
không chứng minh Colab, Drive hay GPU đang dùng được và cũng không xác nhận
benchmark đã hoàn tất hoặc đạt chất lượng. Nếu runner dừng vì lỗi, hãy xử lý lỗi
rồi chạy lại để resume từ checkpoint hợp lệ.

Kiểm chứng 15/10/2026: sau khi smoke một chunk đạt, main chạy script với
`--restart-kernel` trên runtime T4 đang có. Script restart thành công, bootstrap,
nạp model và báo resume `1/18`, bắt đầu chunk `ch01-0001`. Bộ test repo đạt
92 test và 23 subtests. Sau đó các chunk `ch01-0001`, `ch01-0002` và
`ch02-0000` hoàn tất; tại quan sát gần nhất là 4/18, đang xử lý `ch02-0001`.
Đây là trạng thái theo thời điểm, không xác nhận runtime còn sống hay benchmark
đã hoàn tất/chất lượng. Notebook Run all vẫn dùng độc lập; không chạy đồng thời
trên cùng kernel.
