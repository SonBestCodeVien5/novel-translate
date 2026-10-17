# Novel Translate

App đọc truyện cá nhân EN → VI, dữ liệu và SQLite ở máy local; Colab nhận/trả
batch bằng file theo phiên. Mục tiêu là đọc raw/bản dịch/song ngữ nhẹ tại máy;
review và glossary tiếp tục giúp cải thiện bản dịch dần. Ngân sách đã chốt:
**0 đồng**.

P1 vẫn có luồng TXT với **provider giả** để chẩn đoán import, checkpoint, review
và export; nhãn `FAKE` không phải bản dịch thật. Hiện đã có luồng batch thật v2
cho provider `Qwen/Qwen3.5-4B`: tạo job trong app local, chạy/resume manifest
bằng notebook Colab trên Drive, nhập kết quả về local, review/duyệt theo
job và export TXT hoặc EPUB. Có glossary, nhập nhiều result và backup/restore.
P1 fake và batch thật là hai luồng riêng. Trang P1 hiện cho đọc raw khi chưa có
job; app chưa có trang đọc riêng hay nhớ vị trí đọc. Trang đọc riêng và vị trí
đọc là backlog, chưa triển khai.
Xem [hướng dẫn sử dụng batch](docs/REAL_BATCH.md) và
[hợp đồng/trạng thái tích hợp](docs/INTEGRATION.md).

Notebook batch là fallback file-flow; có [script Colab v2](docs/COLAB_V2.md)
và nút chạy/resume cho alias đã đăng ký. Tokenizer local được cài bằng extra
`tokenizer`; local fixture pipeline đã kiểm thử bằng tokenizer Qwen3.5 thật và
generation giả. Live smoke T4 ngày 16/10/2026 đạt trên fixture 2 chương/2 chunk
(input 123/123, output 36/34 token EOS), gồm resume sau restart kernel cùng VM; chưa kiểm mất VM/new VM, toàn bộ 390
chương, benchmark tốc độ/chất lượng hay reader EPUB. P0 metrics chưa được lưu trong
repo; benchmark đã chốt provider Qwen3.5 và được giữ như lịch sử tại
[archive/p0](archive/p0/README.md). Không cần chạy lại để dùng app.

Mốc 4 phiên/2 lần thử mỗi model là ngân sách benchmark P0 lịch sử, không phải
trần mọi lượt dịch sách; số phiên thực tế tùy quota/runtime. Hướng reader và
backlog: [ROADMAP](docs/ROADMAP.md); đánh giá hiện trạng:
[DIRECTION_REVIEW](docs/DIRECTION_REVIEW.md).

Trạng thái mới nhất và thứ tự làm tiếp nằm ở
[bàn giao](docs/HANDOFF.md); tiến độ/giới hạn nằm ở
[ROADMAP](docs/ROADMAP.md). Dữ liệu và backup local không được đẩy lên Git.

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
Colab CLI extra `colab` cần Python 3.12+; xem [hướng dẫn v2](docs/COLAB_V2.md).
Mở <http://127.0.0.1:8000>. Giữ bind loopback: bản này dành cho một người dùng
local. Dữ liệu mặc định ở `data/` (được bỏ qua trong Git); biến môi trường
`NOVEL_DATA_DIR` chọn thư mục local khác. Không đặt SQLite trên Drive.
Khi dùng bàn phím, Tab đầu tiên hiện **Bỏ qua điều hướng**; Enter chuyển tới
nội dung chính. Các trang có title riêng và nút lưu chunk được đọc kèm chương/chunk.

## Thử luồng P1

1. Nhập tên và TXT UTF-8 nhỏ (tối đa 1 MiB), xem trước thứ tự chương, sửa tiêu đề rồi xác nhận.
2. Tạo job giả, chạy từng chunk. Có thể dừng server rồi chạy lại cùng thư mục
   dữ liệu; job và kết quả đã nhận vẫn còn. Tải lại trang sau restart trước khi
   gửi form vì mã CSRF của phiên thay đổi.
3. Tải manifest JSON hoặc nhập result JSON qua form. Result phải đúng snapshot,
   schema và checksum; nhập trùng là no-op, xung đột được báo lỗi.
4. Chọn chương bằng danh sách tên/số thứ tự hoặc nút chương trước/tiếp; trang
   mặc định mở chương đầu và chỉ tải chunk của chương đang xem. Sửa từng chunk
   và lưu sẽ quay lại đúng chương. Hai tab sửa từ cùng revision sẽ báo conflict;
   kết quả máy đến sau không ghi đè bản sửa.
5. Xuất TXT sau khi đủ kết quả, hoặc chọn xuất nháp có đánh dấu phần thiếu.
   Thứ tự chương/chunk được giữ khi xuất, ưu tiên bản sửa tay.

Nguồn gốc, batch, result và bản sửa được giữ riêng. File nhập bị từ chối được
giữ để chẩn đoán; chúng có thể chứa nội dung sách. Không chia sẻ hoặc commit
thư mục dữ liệu. Dùng **Backup và khôi phục** để tải bản sao thư viện;
đừng xóa thư mục dữ liệu để khắc phục lỗi.

## Nhập EPUB local

Ở trang chủ chọn **Nhập EPUB**, tải tệp tối đa 64 MiB; tên sách có thể để trống
để lấy metadata. Nhập lại cùng EPUB trả về sách đã có. CLI vẫn dùng được:

```bash
.venv/bin/python scripts/import_epub.py 'data/Reformat...at_Noble.epub' --data-dir data
```

Giữ EPUB gốc, parse thứ tự spine, lưu text chương trong SQLite cùng mapping
XHTML riêng; import trùng không nhân sách. Không tạo job/dịch tự động. Xem
[luồng EPUB và Colab](docs/EPUB_IMPORT.md).

## Batch dịch Qwen3.5

1. Chạy app local và nhập sách TXT hoặc EPUB ở trang chủ. Mở
   **Glossary** ở trang sách để lưu tên riêng, bản dịch, alias và ghi chú xưng hô,
   rồi chọn **Tạo job Qwen3.5**. Sửa glossary sau đó áp dụng cho job mới;
   job cũ giữ snapshot và các bản sửa tay riêng.
   App dùng tokenizer local pinned, tạo manifest bất biến và mở trang review job.
2. Tải manifest, chọn **Tải notebook Colab**, tải notebook lên Colab, cấp GPU,
   sửa `MANIFEST`/`OUTPUT` thành cùng thư mục Drive của job rồi chạy các cell.
   Notebook bootstrap đúng mã runner; chạy lại cùng manifest/output để resume.
   Nếu đã có alias T4 đăng ký, có thể dùng **Chạy hoặc resume trên Colab** ngay
   ở trang job. Mặc định thử một chunk; để trống giới hạn để chạy phần còn thiếu.
   Kết quả được nhập về sau từng chunk; tải lại trang để xem checkpoint và
   trạng thái process local. Xem [kết nối Colab](docs/COLAB_V2.md).
3. Nhập một result JSON hoặc chọn nhiều JSON/một ZIP ở trang job: tối đa 100
   result, mỗi JSON 1 MiB, tổng 32 MiB. ZIP được kiểm trước; từng result có
   báo cáo đã nhập/trùng/bị từ chối. `manifest.json` trong ZIP được bỏ qua.
   Local validator vẫn kiểm đúng job, checksum/provenance và EOS.
4. Review theo chương, lọc thiếu kết quả/chưa duyệt/đã duyệt; lưu bản sửa hoặc chọn **Lưu và duyệt**.
   Official TXT chỉ xuất được khi mọi chunk của job đó có revision hiện hành đã
   duyệt; draft đánh dấu chunk thiếu/chưa duyệt.

Trang job có **EPUB chính thức** sau khi đủ bản sửa hiện hành đã duyệt. TXT
source tạo EPUB mới; EPUB source giữ mapping/ảnh/link trong profile được hỗ trợ.
Nếu số đoạn hoặc định dạng inline không ánh xạ chắc chắn, app báo cần review;
không xuất file mất nội dung. Xem [giới hạn EPUB](docs/EPUB_EXPORT.md).

Progress đếm result đã import vào local Store, không phản ánh runtime Colab còn
sống. Không tải DB/raw lên Colab; không dùng P0 JSON với v2. Xem
[các bước chi tiết và giới hạn](docs/REAL_BATCH.md).

## Backup và khôi phục

Mở **Backup và khôi phục** → **Tạo và tải backup**. ZIP chứa SQLite cùng nguồn,
mapping, batch, result và sửa tay; không chứa Colab credentials hoặc file ngoài
phạm vi app. Upload backup để khôi phục vào một thư mục mới bên cạnh thư viện
hiện tại; app hiển thị đường dẫn/lệnh mở bản khôi phục. Thư viện đang chạy được
giữ nguyên. UI nhận ZIP tối đa 64 MiB, CLI tối đa 512 MiB; restore nguyên tử
hiện hỗ trợ Linux/WSL. Xem [hướng dẫn backup](docs/BACKUP.md).

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
- [Lịch sử benchmark P0 và profile đã lưu](archive/p0/README.md)
- [Tổng quan](docs/PROJECT_KNOWLEDGE.md)
- [Workflow](docs/WORKFLOW.md) và [quy tắc agent](AGENTS.md)

User đã chọn Qwen3.5 làm provider tích hợp; xem [batch dịch Qwen3.5](docs/REAL_BATCH.md).
Bằng chứng và giới hạn hiện hành ở HANDOFF.
