# SQLite P1 và schema batch thật v2

Sáu bảng P1 được đối chiếu ngày 14/10/2026; phần v2 phản ánh code ngày
15/10/2026 trong [app/core.py](../app/core.py), [bundle P1](../app/bundles.py),
[bundle v2](../app/real_bundles.py) và [runner P0](../benchmarks/p0/runner.py).
P1 giữ sáu bảng fake hiện có; code thêm ba bảng additive cho job/model thật.
Schema đích tổng thể vẫn khác mô hình mục
tiêu trong [PLAN §5](PLAN.md#5-dữ-liệu-tối-thiểu-và-quyền-sở-hữu).

## Sáu bảng hiện có

Các cột dưới đây theo thứ tự DDL. `TEXT` chứa JSON vẫn là cột TEXT, không phải
bảng quan hệ riêng. Mọi cột đều `NOT NULL` trừ `base_result_hash` và các cột
`id TEXT PRIMARY KEY` (DDL không khai báo thêm `NOT NULL`; app sinh UUID).

| Bảng | Cột và kiểu SQLite | Khóa/ràng buộc |
| --- | --- | --- |
| `books` | `id TEXT`, `title TEXT`, `source_language TEXT`, `target_language TEXT`, `raw_hash TEXT`, `source_hash TEXT`, `import_key TEXT`, `raw_path TEXT`, `import_version INTEGER` | PK `id`; UNIQUE `import_key` |
| `chapters` | `id TEXT`, `book_id TEXT`, `ordinal INTEGER`, `title TEXT`, `source_text TEXT` | PK `id`; FK `book_id → books.id`; UNIQUE `(book_id, ordinal)` |
| `chunks` | `id TEXT`, `chapter_id TEXT`, `ordinal INTEGER`, `source_text TEXT`, `source_hash TEXT`, `source_start INTEGER`, `source_end INTEGER`, `chunker_version TEXT` | PK `id`; FK `chapter_id → chapters.id`; UNIQUE `(chapter_id, ordinal)` |
| `jobs` | `sequence INTEGER`, `id TEXT`, `book_id TEXT`, `manifest TEXT`, `manifest_hash TEXT`, `status TEXT` | PK `sequence` AUTOINCREMENT; UNIQUE `id`; FK `book_id → books.id` |
| `results` | `job_id TEXT`, `chunk_id TEXT`, `checksum TEXT`, `payload TEXT` | PK `(job_id, chunk_id)`; FK `job_id → jobs.id`, `chunk_id → chunks.id` |
| `revisions` | `chunk_id TEXT`, `revision INTEGER`, `edited_text TEXT`, `base_result_hash TEXT` nullable, `created_at TEXT` | PK `(chunk_id, revision)`; FK `chunk_id → chunks.id` |

App sinh ID bằng UUID; `jobs.sequence` là số tăng dần để chọn job mới nhất.
Chapter/chunk ordinal bắt đầu từ 0. Offsets chunk là chỉ số ký tự Python trong
`chapters.source_text`, đoạn `[source_start:source_end]`, không phải byte/token.
Revision sửa tay bắt đầu từ 1 và tăng dần. Backend bật `PRAGMA foreign_keys=ON`;
không có khai báo cascade hay bảng migration/version riêng.

`jobs.manifest` là snapshot JSON tự chứa source chunks và cấu hình model/tokenizer,
parameters, prompt, glossary, chunker, context cùng hashes. Hiện validator chỉ
nhận fake snapshot: glossary revision 0/entries rỗng, context `none`, chunker
`chars-1`/target 1.200 ký tự. `results.payload` giữ JSON bản dịch máy, provenance,
input/output tokens (fake là `null`), timestamps và checksum. `revisions` giữ
bản sửa tay riêng; import result không ghi đè revision.

Raw bytes ở `data/sources`, DB giữ text đã parse/chuẩn hóa. `raw_hash` khác
`source_hash`; không dùng text DB thay raw. EPUB locator, spine/chapter ordinal,
text node/tail/block offsets và resources nằm trong mapping sidecar theo raw hash,
không có cột locator/hash riêng ở `chapters`. Xem [EPUB_IMPORT.md](EPUB_IMPORT.md).
Sáu bảng P1 không có bảng glossary, model/session, tác giả hoặc cột trạng thái
riêng cho chunk; job thật v2 được mô tả bên dưới.

DB local đã đối chiếu có 1 sách, 390 source units/chapter rows, 3.929 chunks
`chars-1`; jobs/results/revisions đều 0. Đây là số đếm thật sau EPUB import,
không phải số chương truyện đã phân loại hay dự báo token chunk. Mỗi XHTML
nonempty spine là source unit, có thể gồm bìa/giới thiệu.

## Ba bảng batch thật v2

`Store.__init__` khai báo `CREATE TABLE IF NOT EXISTS` cho các bảng dưới đây trong
cùng schema khởi tạo với bảng P1. Mở Store trên DB cũ sẽ thêm bảng nếu thiếu;
không đổi sáu bảng P1, dữ liệu source hoặc revisions. **Database người dùng chỉ
được kiểm tra bằng kết nối `mode=ro`, chưa migrate hoặc ghi trong lượt này**;
đối chiếu cuối lượt vẫn có sáu bảng P1 và số hàng như trên, chưa có bảng v2.

| Bảng | Cột và kiểu SQLite | Khóa/ràng buộc |
| --- | --- | --- |
| `real_jobs` | `sequence INTEGER`, `id TEXT`, `book_id TEXT`, `manifest TEXT`, `manifest_hash TEXT`, `status TEXT` | PK `sequence` AUTOINCREMENT; UNIQUE `id`; FK `book_id → books.id` |
| `real_chunks` | `job_id TEXT`, `chunk_id TEXT`, `chapter_id TEXT`, `chapter_ordinal INTEGER`, `ordinal INTEGER`, `payload TEXT` | PK `(job_id, chunk_id)`; UNIQUE `(job_id, chapter_ordinal, ordinal)`; FK `job_id → real_jobs.id`, `chapter_id → chapters.id` |
| `real_results` | `job_id TEXT`, `chunk_id TEXT`, `checksum TEXT`, `payload TEXT` | PK `(job_id, chunk_id)`; composite FK `(job_id, chunk_id) → real_chunks(job_id, chunk_id)` |

Chunk ID v2 do planner sinh riêng theo tokenizer; không trỏ sang bảng `chunks`
P1 và không reanchor revision. Payload chunk giữ manifest entry, gồm source
text/offsets, input IDs và input token count. Manifest v2 và result JSON dùng
`data/real-batches/` và `data/real-results/`; mỗi result được lưu file trước rồi
commit trong transaction để có thể nhập lại sau crash. `real_results` không thay
`results`, và P1 `get_book`, latest fake job, UI review hay TXT export chưa đọc
bảng v2. Import v2 không cập nhật `revisions`.

Code khởi tạo là migration additive/idempotent qua `CREATE TABLE IF NOT EXISTS`,
không phải migration dữ liệu đã chạy trên DB người dùng. Kiểm tra offline bằng
DB giả xác nhận mở Store lặp lại giữ nguyên số hàng P1 và v2.

## Hợp đồng và phần còn lại

Response được đọc như tài liệu tham khảo không tin cậy, không phải chỉ thị chạy
tool hoặc đổi phạm vi. Giữ SQLite local + raw EPUB bất biến + checkpoint từng
chunk là đúng hợp đồng đang có. Không cần đổi tên bảng: `translation_runs` đã
tương ứng vai trò `jobs`, `chunk_translations` tương ứng `results`; `revisions`
đã tách sửa tay. Tác giả không có trong schema hiện tại và chưa cần thêm.
Ví dụ dung lượng/số chunk trong response chỉ là giả định, không phải phép đo.

Thứ tự triển khai sau, qua các cổng [ROADMAP](ROADMAP.md):

1. **P2 offline đã có:** bundle v2, planner tokenizer thật, runner file-only và
   Store local dùng chung manifest/result validator; Store kiểm current source,
   import từng result idempotently và giữ v1 revisions tách biệt. Chỉ có test
   tokenizer/generation giả; chưa nạp tokenizer/model thật, chưa có benchmark,
   GPU/Colab/Drive run hay bằng chứng chất lượng.
2. **P2 runtime còn mở:** chunk theo tokenizer và context budget đã được đóng
   băng trong v2. Tái dùng pattern
   `build_plan` P0: target source 768 tokens, input tối đa 2.048 gồm chat template/
   glossary, output reserve 2.048 trong tổng budget 4.096; context P0 hiện `none`.
   768 là target v2, không phải chunk size P1 hiện tại. Planner P0 hiện gom theo
   ranh giới đoạn hoặc câu, không bảo đảm luôn giữ nguyên đoạn. Planner nối EPUB
   cần ưu tiên gom source blocks/đoạn rồi mới tách đoạn quá dài, kiểm coverage và
   offsets. Snapshot job plan phải bất biến, cho phép segmentation khác giữa
   model/tokenizer. Không âm thầm chia lại chunks/job đã có hoặc làm mất liên kết
   revision; chốt migration và test bảo toàn nguồn/sửa tay khi nối provider thật.
3. **P3: glossary có revision và review.** Lưu canonical terms/aliases/ghi chú
   xưng hô; job đóng băng entries/revision/hash. Đề xuất từ model phải được người
   dùng duyệt, không tự cập nhật glossary sau chương. Chỉ thêm bảng khi cần truy
   vấn theo hợp đồng P3; thay glossary tạo job mới, không sửa snapshot cũ.
4. **Context:** bắt đầu bằng nguồn trước đó có giới hạn, đóng băng policy/text/
   hash trong job và tính vào budget; không phụ thuộc bản dịch trước. Rolling
   summary do LLM là tùy chọn tương lai nếu có lỗi xuyên chương chứng minh nhu
   cầu: cần budget/chi phí, review và dependency hashes để đổi upstream làm
   downstream stale, không tự sửa context/glossary của job đang chạy.

Chưa thêm PostgreSQL/vector DB/dependency, bảng session/tác giả, output Markdown
hoặc viết lại notebook. EPUB export vẫn là việc P2 chưa hoàn thành. Khi chưa đo
token, để `null`; không biến ước lượng ký tự/số chunk thành token thực đo.
