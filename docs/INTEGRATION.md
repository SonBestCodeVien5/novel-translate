# Trạng thái tích hợp app và model

Ngày 15/10/2026 user xác nhận đã chấm và chọn `Qwen/Qwen3.5-4B` làm provider
tích hợp. Repo chưa có báo cáo/số đo benchmark để ghi nhận mức tiết kiệm 25%,
18/18 chunks, chạy đủ hai model hay zero critical errors. File criteria hiện
còn `measurements_status=not_run`, `decision=null`; đây là artifact chưa cập nhật,
không phủ định xác nhận của user. Chưa kết luận formal P0 quality gate/phase
đạt. Tài liệu này theo dõi triển khai hiện có và phần runtime còn lại; xem
[P0_MODELS lưu trữ](../archive/p0/docs/P0_MODELS.md) để biết mốc profile tích hợp.

## Readiness có bằng chứng

| Hạng mục | Đã có | Còn thiếu / kết luận |
| --- | --- | --- |
| Local app/review | UI giữ P1 fake riêng và có trang real-job, import, edit/approve, TXT draft/official theo job | Dữ liệu v1 không tự chuyển sang v2; hai luồng vẫn riêng |
| Batch v2 offline | Immutable manifest, runner EOS/checkpoint, local import/status CLI; [schema](SQLITE_SCHEMA.md), [REAL_BATCH](REAL_BATCH.md) | Main đã kiểm fixture 2 chapters/3 chunks với tokenizer Qwen3.5 thật + generation giả, resume, reverse import/duplicate, late edit, approval/official TXT; không phải model/GPU/Drive proof |
| Qwen3.5 profile | User chọn `Qwen/Qwen3.5-4B`; v2 hỗ trợ revision pin `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`, Transformers 5.3 profile, text-only loader, SDPA, `enable_thinking=false`; tokenizer real load/plan fixture đạt | Live T4 inference trên fixture 2 chương/2 chunk, đúng pins; chưa kiểm full book/VM loss hoặc benchmark chất lượng/tốc độ |
| P0 quality | User xác nhận đã chấm và chọn model | Báo cáo/số đo chưa lưu trong repo; không suy ra 25%, 18/18, đủ hai model hoặc zero critical errors. `criteria.json` còn stale (`not_run`/`null`) |
| P0 → v2 | Có JSON plan/results/sessions P0 | Schema khác v2; không đổi tên field, import hoặc dựng provenance giả để nối |
| Store/revision | Bốn bảng `real_*`, gồm `real_revisions(job_id, chunk_id, revision, edited_text, base_result_hash, approved, created_at)`; routes review/save/approve | Live resume/import giữ edit đã duyệt và pending; revisions v2 không reanchor v1 |
| Import/export | UI nhập EPUB, một/nhiều JSON hoặc ZIP; TXT draft/official và EPUB official theo job | Official TXT→EPUB→parser roundtrip 2 chương đạt; EPUB có profile mapping giới hạn, native reader còn cần mở thử |
| Backup/restore | ZIP versioned, SQLite backup API + assets; restore sang thư mục mới, hỗ trợ schema v1 và v2 | Linux/WSL atomic publish; UI upload 64 MiB, CLI 512 MiB; đã backup thư viện thật và thử restore/migration trên bản riêng |
| Glossary | Editor theo sách, revision chống ghi đè, snapshot entries/revision/hash trong job mới; cùng prompt planner/runner | Job cũ giữ snapshot cũ; glossary quá lớn có thể vượt token budget |
| Điều phối | Script v2 và nút start/resume dùng alias/kernel T4 đã đăng ký, notebook fallback cùng runner | Live fixture 2 chunk: `--limit 1`, restart kernel cùng VM, Drive checkpoint byte-identical, resume/import/duplicate no-op; browser nút thu 2 duplicate. Cần Drive đã mount, pins đúng, kernel idle; không tự tạo/giải phóng VM |

## Luồng tích hợp đích

```text
Local Store/UI → immutable v2 manifest → Drive → notebook runner
    → từng completed EOS result → upload local validated Store
    → review/approve revision v2 → TXT draft / TXT official → EPUB sau
```

Store local là chủ sở hữu SQLite. Bundle/runner trên Colab chỉ nhận file; không
mở DB hoặc biến Colab thành backend luôn bật. Giữ raw source, source text,
manifest và machine result bất biến; bản sửa là revision riêng. Import result
không thay bản dịch đang chọn khi job mới về. Review v2 khóa theo `(job_id,
chunk_id)` vì chunking/tokenizer có thể khác v1; không reanchor vào chunk v1 và
không đè revision v1. Lưu revision dùng optimistic check trên base revision và
base result hash. Export TXT draft phải nhận diện chunk thiếu/stale; official
chỉ khi đủ chunk hợp lệ và người dùng chủ động duyệt/chọn job. EPUB export
dùng mapping spine/resource đã nhập và từ chối alignment không chắc chắn.

Đây là luồng UI/file đã triển khai. Main đã chạy local fixture 2 chapters/3
chunks bằng tokenizer thật + generation giả, bao gồm resume, reverse import,
duplicate, late edit, approval và official TXT; snapshot cũ byte-identical. Live
T4 smoke riêng trên fixture 2 chương/2 chunk dùng pins đúng, input tokenizer
123/123 và output 36/34 token EOS. Lượt đầu `--limit 1` import result đầu; sau
restart kernel cùng VM, lượt resume import result hai, xác nhận checkpoint Drive
đầu byte-identical, duplicate no-op và giữ edits đã duyệt/pending. Nút UI trên job
hoàn tất cũng chạy, thu hai duplicate.
Progress là số result đã import local, không
phải trạng thái runtime. Không có tự chọn job mới thay selection, không ghi đè
manual revision khi result đến muộn. SQLite local là chủ sở hữu duy nhất.

## Thứ tự và task packets

### P2-01 — Profile thật tương thích v2 (đã triển khai offline)

- **Đã có:** hỗ trợ Qwen3.5 pin bằng profile tương ứng P0; mapping
  `BatchEncoding` → token IDs, đọc nested config/provenance, Transformers 5.3,
  SDPA, context `max_position_embeddings` và missing-key/loading checks. Đặt
  `chat_template_kwargs: {enable_thinking: false}` trong snapshot/hash và dùng
  đúng cùng tham số ở planner/runner; không lấy mutable P0 `CONFIG` làm profile
  production. Dùng profile này làm mốc cấu hình tích hợp cho model user đã chọn;
  không tự thay model/config hoặc sửa ngầm snapshot/result cũ. Result v2 phải ghi
  provenance thực. P0 profile là pattern cấu hình, không phải số đo benchmark.
- **File/caller dự kiến:** `app/real_bundles.py`, `app/real_runner.py`,
  `scripts/real_batch.py`; caller `scripts/real_batch.py` và runner file-only;
  tests `test_real_bundles.py`, `test_real_runner.py`, `test_real_store.py`;
  cập nhật `REAL_BATCH.md`/snapshot profile nếu hợp đồng đổi. Không nối schema
  P0 results.
- **In/out:** manifest v2 có revision/template/budget/provenance pinned; mỗi
  result chỉ completed khi EOS và hashes/provenance đúng manifest.
- **Kiểm tra đã chạy:** tokenizer Qwen3.5 thật, generation giả trên fixture nhỏ;
  build 2-chapter/3-chunk manifest, interrupt/resume, import ngược thứ tự +
  duplicate, manual edit trước result, approval và official TXT đều đạt; snapshot
  cũ byte-identical. Đây không phải inference/GPU/Drive proof.
- **Còn lại:** live smoke T4 trên fixture nhỏ đã đạt; còn kiểm mất VM/new VM,
  full book và chất lượng/tốc độ. Giữ snapshot v2 cũ validate được; không đổi
  fields/schema hoặc config snapshot cũ.

### P2-03 — Runtime Colab/file checkpoint (đã smoke giới hạn; còn mở full durability)

- **Mục tiêu:** thử manifest v2 nhỏ trên fixture tự tạo có quyền, checkpoint
  ngoài VM, ngắt/resume bằng đọc lại Drive/file. Không cấp GPU thêm trong task.
- **File dự kiến nếu cần:** hướng dẫn `REAL_BATCH.md`,
  `HANDOFF.md`; caller runner/CLI chỉ sửa khi có lỗi chứng minh. Tests fixture
  nhỏ synthetic cho fault cases; không đưa novel có bản quyền vào repo.
- **In/out:** một manifest được pin và result file hoàn tất; readback hash,
  import local validated Store; ngắt xong bỏ qua result hợp lệ và chạy phần thiếu.
- **Đã kiểm live:** truyền file, T4 inference/EOS, checkpoint Drive đọc lại byte-identical,
  restart kernel cùng VM và resume chunk còn lại trên fixture 2 chunk. Chưa kiểm
  mất VM/new VM, full 390 chương, timeout live hay benchmark tốc độ/chất lượng.
- **Dừng:** auth/quota/quyền, hash mismatch, hoặc vượt ngân sách; giữ bằng chứng,
  không retry vô hạn hay tự cấp runtime.

### P2-04 — Colab CLI orchestration (live smoke đạt trên fixture nhỏ)

`scripts/run_colab.py` dùng alias đã đăng ký, kiểm assignment/kernel T4 idle,
pins và Drive; chạy/import từng chunk rồi tiếp tục với model trong cùng kernel.
Có giới hạn chunk, wall timeout, process lock theo kernel và dry-run local.
Nút start/resume ở trang job chạy script bằng fixed argv, không shell; progress
là checkpoint đã import, trạng thái process local được hiển thị riêng. Script
không tạo hoặc tự giải phóng runtime; người dùng giữ quyền vòng đời GPU.
Xem [COLAB_V2](COLAB_V2.md). Các mục dưới là hợp đồng kiểm chứng runtime:

- **Mục tiêu:** script local nối job → alias/kernel T4 đã đăng ký → runner → nhận/validate/import;
  notebook vẫn dùng cùng runner làm fallback. Không tự tạo hay giải phóng VM.
- **File/caller dự kiến:** script điều phối tối thiểu và `scripts/real_batch.py`;
  config/extra CLI chỉ nếu cần. Test runner/Store/CLI hiện có và fault fixtures.
- **In/out:** chọn rõ job ID, cùng manifest/result contract/checkpoint P2-01;
  không service/queue luôn bật, không import toàn bộ batch thiếu kiểm tra.
- **Đã kiểm live:** `--limit 1`, kernel restart cùng VM rồi resume; UI start/resume
  trên job hoàn tất thu hai duplicate. Checkpoint/import idempotency và bảo toàn edits đạt.
- **Còn kiểm:** mất VM/new VM, full 390 chương, generation timeout live, hiệu năng/chất lượng.

### P3-03 / P3-01 — UI review v2 và revision (đã triển khai offline)

- **Đã triển khai:** `app/core.py`, routes `app/main.py`, templates `book.html`/
  `real_job.html`; job được chọn tường minh, revision theo `(job_id, chunk_id)`,
  base revision/result hash, TXT draft/official. Import không ghi đè edit; official
  yêu cầu mọi chunk có revision hiện hành được duyệt.
- **Kiểm tra đã chạy:** main fixture local bằng tokenizer thật + generation giả,
  có reverse import, late edit, approval và official TXT. Full suite app ngày 16/10/2026 đạt 121 passed, 23 subtests (22.30s; 3 warnings).
  Live T4/Drive evidence được ghi riêng ở đầu tài liệu; không chứng minh full-book
  runtime hoặc chất lượng dịch.
- **Còn lại:** automated tests trong full suite bao phủ concurrency, CSRF và XSS;
  kiểm tra accessibility bằng bàn phím/screen reader vẫn chưa làm. Progress
  local không đại diện runtime liveness.

### P3-01 — Glossary theo sách

- Editor có term, translation, aliases, ghi chú; backend kiểm cấu trúc/giới hạn
  và tên trùng. Lưu bằng base revision để tránh hai tab ghi đè.
- `book_glossaries` lưu bản hiện hành; `Store.create_real_job` đóng băng toàn bộ
  glossary/revision/hash vào bản sao snapshot, cho cả UI và CLI.
- Planner và runner cùng dựng prompt từ entries, tính đủ vào input budget;
  snapshot rỗng cũ giữ nguyên input/hash. Đổi glossary không sửa manifest,
  result hoặc manual revision của job cũ. Review hiển thị khác revision.
- Kiểm chứng glossary ngày 16/10 (trước live runtime smoke): full suite app
  78 passed/23 subtests; 40 test P0 lưu trữ đạt riêng. Main kiểm byte compatibility
  snapshot/messages/manifest cũ; Playwright thêm/sửa/xóa và thêm bằng bàn phím
  trên fixture local đạt. Live T4/Drive smoke sau đó đạt 2 chunk; mất VM/new VM/full book còn mở.

### P2-02 / P3-02 — EPUB và backup

- EPUB upload web/CLI giữ raw/mapping; official export chia sẻ guard duyệt với
  TXT. TXT tạo EPUB3 mới; source EPUB thay đúng text slot khi count/alignment
  khớp, giữ resources/spine/link. Mixed inline hoặc mismatch báo cần review.
  [Profile EPUB](EPUB_EXPORT.md) không hứa hỗ trợ mọi cấu trúc.
- [Backup](BACKUP.md) gồm SQLite snapshot + asset inventory/hash, bỏ auth/state
  ngoài app; restore không ghi đè. Main đã backup thư viện thật schema v1,
  khôi phục/mở Store trên bản riêng và xác minh 6→11 bảng, raw/source checks
  đạt; app sau đó migrate additive 6→11 bảng, vẫn 1 book/390 chapters/3.929 chunks
  và raw/source giữ nguyên. Native EPUB reader còn cần mở thử.

Phần hợp đồng kiểm chứng còn lại:

- **Mục tiêu:** EPUB export/roundtrip; backup/restore DB cùng assets.
- **File/caller dự kiến:** `app/core.py`, `app/epub.py`, `app/main.py`,
  `scripts/import_epub.py`/export CLI khi có; tests `test_epub.py`, `test_core.py`,
  `test_web.py`; fixture EPUB giả/tự tạo; docs hướng dẫn.
- **In/out:** snapshot glossary bất biến; giữ locator/spine/resources; backup
  nhất quán; không tái dịch hoặc thay revision âm thầm.
- **Kiểm tra dự kiến (chưa chạy):** glossary đổi giữa job; EPUB roundtrip bằng
  parser và reader; backup restore; ký tự escape/link/ảnh/spine.
- **Dừng:** nếu mapping không thể giữ nguyên cấu trúc EPUB thì báo lỗi/review,
  không xuất file có vẻ thành công.

## Acceptance end-to-end dự kiến

Fixture nhỏ tự tạo, pipeline local → file/Drive → runner → local Store → review
→ TXT. Phải chứng minh: import cùng result lặp lại là no-op; payload khác cùng
job/chunk là conflict; file partial/checksum sai bị từ chối mà không mất dữ liệu;
nguồn hoặc manifest stale bị giữ riêng; crash sau ghi file nhưng trước commit
có thể nhập lại; result tới muộn sau edit không đổi revision; hai tab stale bị
409/conflict; `max_tokens`, token budget vượt hoặc thiếu EOS không thành complete;
chunk order theo manifest dù result tới lộn thứ tự; restart chỉ bỏ qua checkpoint
đã đọc lại và xác minh. TXT official đòi đủ chunk và duyệt rõ. Các bước này là
tiêu chí tương lai, chưa chạy trong lượt chuẩn bị.
