# Novel Translate

Ứng dụng cá nhân EN → VI, dữ liệu và SQLite ở máy local; Colab xử lý batch
theo phiên ở giai đoạn sau. Ngân sách đã chốt: **0 đồng**.

Bản đầu P1 hỗ trợ TXT với **provider giả**, dùng để kiểm tra luồng nhập,
checkpoint, review và xuất. Nội dung có nhãn `FAKE`, không phải bản dịch thật.
Chưa có provider thật trong app, EPUB, crawler hoặc kết quả benchmark chất lượng. Notebook đã lưu GPUcheck Tesla T4, chưa có bằng chứng model đã chạy. Đã chuẩn bị [notebook P0](notebooks/p0_benchmark.ipynb) tự chứa mã, chỉ cần corpus riêng trên Drive; chưa chạy model. Nguồn người dùng chọn cho P0 là [Reformation of the Deadbeat Noble](https://www.webnovel.com/vi/book/27050623305192205/72613479139302959), theo thứ tự Webnovel 1–5 **có Prologue**. Người dùng đã cung cấp hai TXT đầu, thân tiếng Anh với heading tiếng Việt; còn thiếu chương 3–5 và chưa chứng minh quyền dùng nguồn.

## Chạy local

Cần Python 3.11 trở lên. Tại root repo, dùng `uv`:

```bash
UV_CACHE_DIR=/tmp/novel-translate-uv-cache uv venv .venv
UV_CACHE_DIR=/tmp/novel-translate-uv-cache uv pip install --python .venv/bin/python -e '.[test]'
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Nếu đã có pip, có thể dùng `python3 -m venv .venv` rồi
`.venv/bin/python -m pip install -e '.[test]'` thay hai lệnh đầu.
Mở <http://127.0.0.1:8000>. Giữ bind loopback: bản này dành cho một người dùng
local. Dữ liệu mặc định ở `data/` (được bỏ qua trong Git); biến môi trường
`NOVEL_DATA_DIR` chọn thư mục local khác. Không đặt SQLite trên Drive.

## Thử luồng P1

1. Nhập tên và TXT UTF-8 nhỏ (tối đa 1 MiB), xem trước thứ tự chương, sửa tiêu đề rồi xác nhận.
2. Tạo job giả, chạy từng chunk. Có thể dừng server rồi chạy lại cùng thư mục
   dữ liệu; job và kết quả đã nhận vẫn còn. Tải lại trang sau restart trước khi
   gửi form vì mã CSRF của phiên thay đổi.
3. Tải manifest JSON hoặc nhập result JSON qua form. Result phải đúng snapshot,
   schema và checksum; nhập trùng là no-op, xung đột được báo lỗi.
4. Sửa từng chunk và lưu. Hai tab sửa từ cùng revision sẽ báo conflict;
   kết quả máy đến sau không ghi đè bản sửa.
5. Xuất TXT sau khi đủ kết quả, hoặc chọn xuất nháp có đánh dấu phần thiếu.
   Thứ tự chương/chunk được giữ khi xuất, ưu tiên bản sửa tay.

Nguồn gốc, batch, result và bản sửa được giữ riêng. File nhập bị từ chối được
giữ để chẩn đoán; chúng có thể chứa nội dung sách. Không chia sẻ hoặc commit
thư mục dữ liệu. P1 chưa có giao diện backup/restore; đừng xóa thư mục dữ liệu
để khắc phục lỗi.

## Kiểm tra

```bash
.venv/bin/python -m pytest
```

Fixture là đoạn tự tạo; không đưa novel thật, secret, `.env` hoặc DB vào repo.
Bằng chứng và giới hạn của đợt triển khai nằm trong [P1.md](docs/P1.md).

## Tài liệu

Phiên mới đọc [AGENTS.md](AGENTS.md) → [WORKFLOW](docs/WORKFLOW.md) →
[HANDOFF](docs/HANDOFF.md); chỉ mở phần PLAN/ROADMAP liên quan nhiệm vụ.

- [Kế hoạch và hợp đồng dữ liệu](docs/PLAN.md)
- [Roadmap và cổng kiểm chứng](docs/ROADMAP.md)
- [Hướng dẫn và phiếu benchmark P0 chưa chạy](docs/P0_BENCHMARK.md)
- [Hai ứng viên model P0](docs/P0_MODELS.md)
- [Tổng quan](docs/PROJECT_KNOWLEDGE.md)
- [Workflow](docs/WORKFLOW.md) và [quy tắc agent](AGENTS.md)

P0 có hai ứng viên và người dùng review; còn thiếu ba TXT (ch03–ch05), xác minh
quyền nguồn, văn phong chi tiết và trần thử nghiệm trước khi chạy/chấm. Output GPUcheck đã lưu ghi Tesla T4; chưa xác nhận runtime hiện tại, quota,
tốc độ hoặc chất lượng model. Corpus smoke đã upload và xác minh trên Drive;
trạng thái và thao tác tiếp theo ở HANDOFF.
