# Novel Translate

Ứng dụng cá nhân EN → VI, dữ liệu và SQLite ở máy local; Colab nhận/trả batch
bằng file theo phiên. Ngân sách đã chốt: **0 đồng**.

P1 vẫn có luồng TXT với **provider giả** để chẩn đoán import, checkpoint, review
và export; nhãn `FAKE` không phải bản dịch thật. Hiện đã có luồng batch thật v2
cho provider `Qwen/Qwen3.5-4B`: tạo job trong app local, chạy/resume manifest
bằng notebook Colab trên Drive, nhập từng result về local, review/duyệt theo
job và export TXT nháp/chính thức. P1 fake và batch thật là hai luồng riêng.
Xem [hướng dẫn sử dụng batch](docs/REAL_BATCH.md) và
[hợp đồng/trạng thái tích hợp](docs/INTEGRATION.md).

Notebook batch là fallback file-flow hiện có; Colab CLI orchestration cho v2
chưa hoàn tất. Tokenizer local được cài bằng extra `tokenizer`; local fixture
pipeline đã kiểm thử bằng tokenizer Qwen3.5 thật và generation giả. GPU/model v2
inference và Drive interruption/resume chưa chạy. P0 quality không được suy ra
từ khả năng tích hợp; trạng thái chấm theo xác nhận user và metrics trong repo
được tách riêng. Các notebook P0 cũ giữ quy trình benchmark độc lập.
Đã chuẩn bị
[notebook P0](notebooks/p0_benchmark.ipynb) tự chứa mã, dùng corpus riêng trên
Drive. Ba notebook P0 nằm cùng thư mục `notebooks/`: [Qwen3](notebooks/p0_benchmark.ipynb),
[Qwen2.5](notebooks/p0_qwen25_benchmark.ipynb) và
[Qwen3.5-4B](notebooks/p0_qwen35_benchmark.ipynb). Bản Qwen3.5 dùng NF4 4-bit,
float16, batch 1, context 4.096, tắt thinking và mặc định thử một chunk
(`LIMIT=1`); đặt `LIMIT=None` để chạy hết các chunk còn lại sau khi kiểm tra.
Notebook P0 hỗ trợ Run all độc lập. Batch app tải notebook Qwen3.5 riêng qua UI;
Colab CLI orchestration cho v2 chưa hoàn tất. Nguồn mới người dùng chọn cho P0 là [Reformation of the Deadbeat
Noble trên FreeWebNovel](https://freewebnovel.com/novel/reformation-of-the-deadbeat-noble),
nhưng chưa xác minh được mục lục hay đối chiếu với hai TXT mẫu hiện có. Hai TXT
được cung cấp có provenance Webnovel và theo thứ tự chương 1–5 **có Prologue**;
đã đủ năm TXT, chưa chứng minh quyền dùng nguồn; ch03–ch05 chưa xác minh URL và
khác cách viết tên.

## Chạy local

Cần Python 3.11 trở lên. Tại root repo, dùng `uv`:

```bash
UV_CACHE_DIR=/tmp/novel-translate-uv-cache uv venv .venv
UV_CACHE_DIR=/tmp/novel-translate-uv-cache uv pip install --python .venv/bin/python -e '.[test,tokenizer]'
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Nếu đã có pip, có thể dùng `python3 -m venv .venv` rồi
`.venv/bin/python -m pip install -e '.[test,tokenizer]'` thay hai lệnh đầu.
Extra `tokenizer` chỉ cài `transformers==5.3.0`; app local tải tokenizer/config
đã pin, không tải model weights hay cài PyTorch. Notebook cài runtime pins riêng.
Colab CLI extra `colab` cần Python 3.12+ và chưa tự động hóa batch v2.
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

## Batch dịch Qwen3.5

1. Chạy app local và nhập sách TXT như mục P1; ở trang sách chọn **Tạo job Qwen3.5**.
   App dùng tokenizer local pinned, tạo manifest bất biến và mở trang review job.
2. Tải manifest, chọn **Tải notebook Colab**, tải notebook lên Colab, cấp GPU,
   sửa `MANIFEST`/`OUTPUT` thành cùng thư mục Drive của job rồi chạy các cell.
   Notebook bootstrap đúng mã runner; chạy lại cùng manifest/output để resume.
3. Tải từng file result JSON trong thư mục `results` về máy local và upload từng
   file ở trang job (tối đa 1 MiB/file). Local validator chỉ nhận result v2 đúng
   job, manifest, checksum/provenance và EOS; import trùng là no-op.
4. Review chunk theo thứ tự nguồn; lưu bản sửa hoặc chọn **Lưu và duyệt**.
   Official TXT chỉ xuất được khi mọi chunk của job đó có revision hiện hành đã
   duyệt; draft đánh dấu chunk thiếu/chưa duyệt.

Progress đếm result đã import vào local Store, không phản ánh runtime Colab còn
sống. Không tải DB/raw lên Colab; không dùng P0 JSON với v2. Xem
[các bước chi tiết và giới hạn](docs/REAL_BATCH.md).

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
- [Hướng dẫn/phiếu benchmark và metrics còn thiếu P0](docs/P0_BENCHMARK.md)
- [Decision và profile model P0](docs/P0_MODELS.md)
- [Tổng quan](docs/PROJECT_KNOWLEDGE.md)
- [Workflow](docs/WORKFLOW.md) và [quy tắc agent](AGENTS.md)

User đã chọn Qwen3.5 làm provider tích hợp; xem [decision/profile](docs/P0_MODELS.md).
Ghi chú nguồn/provenance P0 dưới đây phản ánh giai đoạn chuẩn bị ngày 14/10.
Sau đó user đã chọn Qwen3.5 làm provider tích hợp; metrics benchmark chưa được
lưu trong repo. Bằng chứng và giới hạn hiện hành ở HANDOFF.
