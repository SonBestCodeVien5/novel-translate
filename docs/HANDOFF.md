# Bàn giao phiên — 14/10/2026 (Asia/Bangkok)

Đọc sau WORKFLOW; đây là trạng thái vận hành, không thay PLAN/ROADMAP.

## Sửa lần chạy Qwen2.5 bị lặp — 14/10/2026

- Notebook người dùng gửi đã tải model trên Tesla T4 và lưu `ch01-0000` rồi
  dừng đúng guard `needs_review`. Đọc checkpoint Drive xác nhận
  `finish_reason=max_tokens`, 2.048 output tokens / 826 input tokens, không có
  exception generation; tám token cuối là `[50994,0,50994,0,50994,0,50994,0]`.
- Notebook Qwen2.5 thêm `repetition_penalty=1.1` trước khi tính snapshot để giảm
  lặp greedy. Snapshot/output mới giữ nguyên kết quả cũ; không tăng reserve,
  không bỏ kiểm tra truncated, không tự retry. Qwen3 giữ nguyên.
- Restart session rồi Run all bằng notebook local đã sửa. Chưa chạy GPU với
  cấu hình mới; chưa chứng minh hết lặp hoặc chất lượng, vẫn giữ trần thử P0.
- Main kiểm offline: 25 passed, 1 deselected. Bộ đầy đủ có 1 failure có sẵn:
  bootstrap Qwen3 chỉ khác `execution_count=3` so với refresh đặt `None`;
  nội dung nhúng khớp source. Syntax/bootstrap Qwen2.5 đạt, không có output lưu.


## Cập nhật ghi chú schema — 14/10/2026

Đã đối chiếu SQLite local: 6 bảng, 1 sách/390 source units/3.929 chunks
`chars-1`, jobs/results/revisions đều 0; foreign key check không có lỗi.
[SQLITE_SCHEMA.md](SQLITE_SCHEMA.md) ghi đầy đủ cột/khóa và chọn lọc response
đính kèm: P2 thống nhất bundle/provider provenance rồi token planner bất biến,
P3 glossary review/snapshot; context nguồn có giới hạn trước rolling summary.
Chỉ cập nhật tài liệu, chưa migration/code/DB/notebook; không coi 3.929 chunks
ký tự là chunk 768 tokens hoặc checkpoint là bằng chứng runtime đang sống.

## Cập nhật EPUB import — 14/10/2026

Người dùng mở riêng phần nhập EPUB local của P2; quy tắc chỉ P0 bên dưới là lịch
sử trước yêu cầu mới. Chưa mở EPUB export/provider sản xuất/CLI Colab điều phối.

- Đã có `scripts/import_epub.py`, parser `app/epub.py`, `Store.import_epub`.
  Đọc [EPUB_IMPORT.md](EPUB_IMPORT.md) cho lệnh chạy và luồng batch/Drive/Colab.
- Đã nhập `data/Reformat...at_Noble.epub` vào `data/library.sqlite3`:
  book ID `9d185dcb-29d3-477a-a5be-3d82649b3580`, 390 source units, 3.929 chunks.
  Một XHTML nonempty spine = một source unit; có thể gồm bìa/giới thiệu.
  Raw EPUB giữ nguyên tại sources/hash.epub; mapping giữ locator/spine ordinal,
  chapter ordinal, node/tail/block offsets/resources. Không tự tách chương trong
  một XHTML hoặc làm EPUB export. UI upload vẫn TXT; job vẫn fake.
- Test EPUB/core: 14 passed, 23 subtests passed. Main kiểm raw byte equality,
  mapping/hash/order, chunk offsets/reconstruction, reimport idempotent, zero jobs.
  Web tests sandbox treo đã dừng; không claim web passed lần này.
- Có backup DB trước nhập bằng SQLite backup API trong data/backups. Main đã nhập
  sớm trước khi worker thêm chapter ordinal metadata; giữ mapping cũ backup rồi
  đối chiếu chỉ metadata bổ sung trước cập nhật final; raw/source/DB text nguyên.
  Metadata riêng: `data/epub-import-verification.json`, data được Git ignore.
- Chưa cài/test Colab CLI, chưa nối schema P0 benchmark với app bundle. Luồng
  dự kiến: backend xuất batch -> Drive -> Colab -> Drive results từng chunk ->
  backend tải/validate/import SQLite, giữ sửa tay. Không upload/mở SQLite ở Colab.


## Cập nhật chuẩn bị full P0 — 14/10/2026

Qwen2.5 đã thêm log trực tiếp tải model, resume count, bắt đầu chunk, thời gian
sinh và checkpoint đã ghi. Cập nhật cùng file Drive và đọc lại đúng bytes.
Qwen3 đang chạy giữ nguyên theo user; chỉ cập nhật khi user báo xong.
Kiểm tra tiến trình offline: 24 passed, 1 deselected (test Qwen3 metadata
execution_count có sẵn khác refresh; không sửa notebook đang chạy).
Cả hai bootstrap/source và syntax kiểm tra passed; chưa thử live Colab.

**Đã gỡ blocker:** user xác nhận upload; corpus full đã lên MyDrive/p0/corpus.json,
đọc lại xác minh đúng 56.873 byte và SHA-256. Có thể chạy notebook Qwen3 Run all,
mount Drive cùng tài khoản. Sau đó dùng phiên GPU riêng cho Qwen2.5.
Thông báo chặn upload dưới đây là lịch sử. Chưa inference/GPU thật.

- Đã nhận đủ 5 TXT; manifest cập nhật heading/hash/count thật. Corpus full
  `data/p0/corpus.json`: 56.873 byte, SHA-256
  `a6b4f14c675f3d9a3ffe7e4adc197da4e36d2f537fc038e90d9783284a138883`.
  Giữ nguyên bytes; ch03–ch05 URL chưa biết, quyền nguồn chưa xác minh.
  Ch01–ch02 dùng Airn, ch03–ch05 dùng Irene; chưa đối chiếu bản nguồn.
- Notebook chuẩn đổi sang `MyDrive/p0/corpus.json`, `LIMIT=None`; thêm biến thể
  Qwen2.5 riêng tại [notebooks/p0_qwen25_benchmark.ipynb](../notebooks/p0_qwen25_benchmark.ipynb). Giữ pins/revisions,
  output riêng từng model/snapshot, không in bản dịch. Hai file local cùng thư mục
  `notebooks/`; mở trong VS Code và chọn Colab hosted GPU kernel hoặc mở trên
  Colab, không chạy bằng local kernel. Baseline làm sau sinh máy
  theo yêu cầu mới, nhưng phải hoàn thành trước khi đọc output.
- Đã upload hai notebook và xác minh metadata/raw file reference readback:
  [Qwen3](https://colab.research.google.com/drive/1htQgvx-qUmH2-Zj-T6F6M64lzS4IFEzZ),
  [Qwen2.5](https://colab.research.google.com/drive/1Hv5qy77ZqZWGCqK6xXGjJAQih6sXQt7J).
  Chưa so bytes tải lại notebook. Mỗi model chạy phiên GPU riêng, cấp auth Drive.
- **Chưa được Run all:** upload corpus full bị automatic approval review từ chối
  hai lần vì đòi xác nhận user cho đúng payload/thư mục, dù metadata xác nhận p0
  thuộc My Drive cùng owner, không shared. Chờ user đồng ý tải corpus 5 chương
  vào [p0](https://drive.google.com/drive/folders/1QgJSEOPOVOfiFxAmyx9tD9vj_GnbQ3Za),
  rồi upload và đọc lại xác minh; không dùng đường vòng. Smoke cũ giữ nguyên.
- Worker gpt-6.1-sol/low chạy 22 test P0 passed; main kiểm tra bytes 5 chương,
  config/compile/bootstrap hai notebook và không có output saved: passed.
  Chưa inference/GPU thật, ngắt/resume thật, token coverage hoặc review chất lượng.
- Metadata riêng: `data/p0/corpus-verification.json`,
  `data/p0/full-drive-preparation.json`; không commit data/novel.

Các mục thiếu ch03–ch05 và default smoke dưới đây là lịch sử đã được cập nhật
bởi mục này; chưa có kết quả benchmark hoặc go/no-go.

Chỉ tiếp tục **P0**, không mở P1/P2 hoặc crawler P4. P1 local fake đã có bằng
chứng trong P1.md; chưa chạy model thật, chưa có benchmark hay go/no-go.

## Đã chốt và còn mở

- EN → VI, ngân sách 0 đồng, Colab free theo phiên tương tác; người dùng tự review.
- Hai ứng viên: Qwen3-4B-Instruct-2507 và Qwen2.5-7B-Instruct; revision,
  package pins và cấu hình ở [P0_MODELS.md](P0_MODELS.md), không tự đổi snapshot.
- Benchmark chính thức: 5 chương × 2 model, không bỏ đoạn, mọi chunk hoàn tất,
  zero critical sau review, tổng thời gian sinh + sửa giảm ≥25% so baseline.
- Người dùng chốt ngày 14/10/2026: tiếng Việt tự nhiên, giữ giọng nhân vật và
  tên riêng; tối đa 2 lần thử/model, tổng 4 phiên Colab miễn phí. Đã ghi
  [criteria.json](../benchmarks/p0/criteria.json); benchmark vẫn chưa chạy.
- Baseline dịch tay cùng toàn bộ chương phải xong trước khi xem output model,
  kể cả hai chương smoke sẽ dùng lại; smoke không chứng minh chất lượng/go-no-go.

## Dữ liệu và bằng chứng hiện có

Người dùng vừa chọn nguồn mới [FreeWebNovel](https://freewebnovel.com/novel/reformation-of-the-deadbeat-noble).
Playwright ngày 14/10/2026 gặp Cloudflare security verification; mục lục và
ch03–ch05 chưa xác minh, không vượt chặn. Hai TXT hiện có vẫn giữ nguyên bytes;
provenance của chúng là Webnovel ([trang sách](https://www.webnovel.com/vi/book/27050623305192205/72613479139302959)),
theo thứ tự 1–5 có Prologue. Chưa đối chiếu chúng có tương đương nguồn FreeWebNovel;
quyền nguồn vẫn unverified. HTTP trực tiếp Webnovel từng trả 403; trạng thái/checkpoint
của cả hai lần thử ở `data/p0/source-check.json`.
Raw/source, machine output và sửa tay giữ riêng; không commit toàn văn hoặc data.

`data/p0/corpus-smoke.json` là corpus v2 hai chương, chỉ đủ smoke. Plugin Drive
đã upload và đọc lại xác minh đúng bytes ngày 14/10/2026 tại cùng tài khoản:
`MyDrive/p0/corpus-smoke.json`, 19.102 byte, SHA-256
`42db593b9738a93129c11da9a75e93c6b1c697ea72183b8eab16844a38ae9957`.
Metadata/link riêng ở `data/p0/drive-upload.json`; không nhờ upload lại file này.
Notebook người dùng lưu có `CUDA: True`, `GPU: Tesla T4`: output đã quan sát,
không chứng minh runtime đang sống, model đã load hay chất lượng dịch.

## Bước tiếp theo

1. Dùng [notebook P0](../notebooks/p0_benchmark.ipynb) hiện tại trên Colab GPU,
   cùng tài khoản Google; người dùng bấm Run all và xác nhận auth mount Drive.
   Chưa có công cụ kết nối để agent chạy kernel Colab của người dùng.
2. Mặc định `CORPUS=/content/drive/MyDrive/p0/corpus-smoke.json`, `LIMIT=1`.
   Notebook tự bootstrap mã vào `/content/p0-code`, không cần repo trên Drive.
   Chưa xem output nếu baseline các chương dùng lại chưa hoàn tất.
3. Output: `/content/drive/MyDrive/p0/runs/<model-short>-<snapshotsha256>`.
   Kiểm tra một chunk, reconnect cùng snapshot, rồi `LIMIT=None` để chạy nốt
   smoke khi phù hợp; ngắt/resume và GPU inference **chưa được kiểm thử thật**.
   Lỗi quyền/OOM/checksum/config thì dừng ghi bằng chứng, không retry vô hạn.
4. Hoàn thiện đúng ch03–ch05, metadata/quyền nguồn, coverage chương dài và các
   quyết định còn mở trước corpus chính thức; xem [P0_BENCHMARK.md](P0_BENCHMARK.md).

## Giữ phiên sau gọn

Giữ model main đang chọn; triển khai giao worker `gpt-6.1-sol`, reasoning `low`,
tối đa hai worker, mỗi file một owner, không lồng worker/heartbeat/poll.
Tiếng Việt ngắn, ponytail full: thay đổi nhỏ nhưng đủ, tái dùng sẵn có, không
thêm dependency/abstraction thừa, không hỏi lại việc đảo ngược đã được cho phép.
Dùng tool Drive có sẵn cho phần được giao trước khi nhờ người dùng làm tay.
Kết thúc báo điều đã làm, kiểm tra thực chạy, phần chưa kiểm và rủi ro.

Notebook nhúng ba file mã tĩnh; sau sửa runner/validator phải tái sinh bằng
`python3 benchmarks/p0/build_notebook.py` và chạy test offline liên quan.
Test offline không chứng minh CUDA, package pins, quyền nguồn hoặc chất lượng.
Runner từ chối `technical_complete` nếu `raw_output_ids` rỗng; đã thêm test và
tái sinh notebook. `timeout 60s .venv/bin/python -m pytest -q` ngoài sandbox:
exit 0, 37 passed, 11 subtests passed, 1 warning (Starlette/httpx deprecated),
2.89s; lần trong sandbox timeout 45s.
Phiên này dùng thành công 2 worker `gpt-6-luna`, reasoning `low`, không monitor;
đây là kết quả runtime riêng, không đổi mặc định staging `gpt-6.1-sol`.
Crawler được bảo vệ sau này phải dùng Playwright, cookies, retry giới hạn và
checkpoint bền vững để resume; chưa mở việc P4 trong phiên này.

Prompt mở phiên mới:
> Đọc AGENTS.md, docs/WORKFLOW.md, docs/HANDOFF.md rồi tiếp tục P0 từ trạng thái đã ghi; không mở P1/P2.
