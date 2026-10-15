# Novel Translate

Ứng dụng cá nhân EN → VI, dữ liệu và SQLite ở máy local; Colab nhận/trả batch
bằng file theo phiên. Ngân sách đã chốt: **0 đồng**.

Bản đầu P1 hỗ trợ TXT với **provider giả**, dùng để kiểm tra luồng nhập,
checkpoint, review và xuất. Nội dung có nhãn `FAKE`, không phải bản dịch thật.
Đã có [CLI nhập EPUB local](docs/EPUB_IMPORT.md) và offline v2 batch/runner local.
V2 mới được kiểm tra bằng tokenizer/generation giả; chưa nối UI, review/export hay
có lần chạy model thật trong luồng v2;
P0 vẫn là pipeline benchmark riêng. Xem [hướng dẫn batch v2](docs/REAL_BATCH.md).
Qwen3.5 đã qua smoke kỹ thuật một chunk trên T4 và script CLI đang resume phần
còn lại trên runtime hiện có. Chưa hoàn tất benchmark hoặc có go/no-go. Không
xem bản dịch trước khi baseline dịch tay xong. Đã chuẩn bị
[notebook P0](notebooks/p0_benchmark.ipynb) tự chứa mã, dùng corpus riêng trên
Drive. Ba bản local nằm cùng thư mục `notebooks/`: [Qwen3](notebooks/p0_benchmark.ipynb),
[Qwen2.5](notebooks/p0_qwen25_benchmark.ipynb) và
[Qwen3.5-4B](notebooks/p0_qwen35_benchmark.ipynb). Bản Qwen3.5 dùng NF4 4-bit,
float16, batch 1, context 4.096, tắt thinking và mặc định thử một chunk
(`LIMIT=1`); đặt `LIMIT=None` để chạy hết các chunk còn lại sau khi kiểm tra.
Notebook hỗ trợ Run all độc lập; cũng có thể dùng [lệnh CLI tự động](docs/COLAB_AUTOMATION.md)
trên runtime Qwen3.5 hiện có. Không chạy hai cách đồng thời trên cùng kernel;
mỗi runtime chạy một model. Nguồn mới người dùng chọn cho P0 là [Reformation of the Deadbeat
Noble trên FreeWebNovel](https://freewebnovel.com/novel/reformation-of-the-deadbeat-noble),
nhưng chưa xác minh được mục lục hay đối chiếu với hai TXT mẫu hiện có. Hai TXT
được cung cấp có provenance Webnovel và theo thứ tự chương 1–5 **có Prologue**;
đã đủ năm TXT, chưa chứng minh quyền dùng nguồn; ch03–ch05 chưa xác minh URL và
khác cách viết tên.

## Chạy local

Cần Python 3.11 trở lên. Tại root repo, dùng `uv`:

```bash
UV_CACHE_DIR=/tmp/novel-translate-uv-cache uv venv .venv
UV_CACHE_DIR=/tmp/novel-translate-uv-cache uv pip install --python .venv/bin/python -e '.[test]'
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Nếu đã có pip, có thể dùng `python3 -m venv .venv` rồi
`.venv/bin/python -m pip install -e '.[test]'` thay hai lệnh đầu.
Để dùng thêm Colab CLI trong cùng `.venv`, dùng Python 3.12+ và cài
`'.[test,colab]'`; xem [Colab CLI](docs/COLAB_CLI.md) để đăng nhập và quản lý kernel.
Luồng Qwen3.5 tự động trên runtime hiện có nằm trong
[COLAB_AUTOMATION.md](docs/COLAB_AUTOMATION.md): kiểm tra môi trường, cập nhật mã,
chạy toàn bộ chunk còn thiếu và giữ checkpoint, không cần bấm từng cell.
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

## Nhập EPUB local

```bash
.venv/bin/python scripts/import_epub.py 'data/Reformat...at_Noble.epub' --data-dir data
```

Giữ EPUB gốc, parse thứ tự spine, lưu text chương trong SQLite cùng mapping
XHTML riêng; import trùng không nhân sách. Không tạo job/dịch tự động. Xem
[luồng EPUB và Colab](docs/EPUB_IMPORT.md); upload UI hiện vẫn chỉ nhận TXT.

## Batch provider thật offline

CLI `scripts/real_batch.py` có `export`, `import` và `status` cho schema v2.
SQLite ở máy local; Colab chỉ nhận manifest/mã runner và trả từng result JSON.
CLI chưa mount Drive, điều phối phiên Colab hay đưa kết quả vào UI P1. Xem
[các bước batch v2 và giới hạn](docs/REAL_BATCH.md).

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
- [Cấu hình các ứng viên model P0](docs/P0_MODELS.md)
- [Tổng quan](docs/PROJECT_KNOWLEDGE.md)
- [Workflow](docs/WORKFLOW.md) và [quy tắc agent](AGENTS.md)

P0 có hai ứng viên ban đầu và notebook Qwen3.5-4B bổ sung; người dùng review.
Tiêu chí văn phong và giới hạn thử nghiệm
đã chốt ngày 14/10/2026. Đã đủ năm TXT và chuẩn bị corpus full; còn xác minh quyền nguồn và
baseline trước khi đọc/chấm output. Playwright gặp Cloudflare security verification ở
cả Webnovel và FreeWebNovel, nên chưa xác minh TOC hay đối chiếu nguồn mới. Output GPUcheck đã lưu ghi Tesla T4; chưa xác nhận runtime hiện tại, quota,
tốc độ hoặc chất lượng model. Hai notebook full đã lên Drive; corpus full đã upload và đọc lại xác minh sau xác nhận của người dùng. Corpus smoke cũ giữ nguyên;
trạng thái và thao tác tiếp theo ở HANDOFF.
