# Bàn giao phiên — 15/10/2026 (Asia/Bangkok)

Đọc sau WORKFLOW; trạng thái mới nhất ở mục đầu, các mục sau là lịch sử.

## Offline pipeline Qwen3.5 và review v2 — 15/10/2026

- User yêu cầu triển khai pipeline và commit. Hai worker triển khai provider/
  notebook và UI; main tích hợp/kiểm chứng. Main đã commit provider/notebook
  `6aff1eb` và UI/review/export `fed9f42`; phần docs đang được cập nhật riêng.
  Provider đã chốt Qwen3.5. Code hiện có v2 bundle/runner, local
  Store/UI review, `real_revisions`, TXT draft/official theo job và notebook
  Colab fallback. P1 fake giữ riêng.
- Qwen3.5 pin `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`; Transformers 5.3.0,
  accelerate 1.11.0, bitsandbytes 0.48.2 ở notebook. Local extra `tokenizer`
  chỉ cài Transformers 5.3; không tải weights. Main tải/load tokenizer pinned thật
  thành công và kiểm input ID/kwargs trên fixture. `enable_thinking=false` nằm trong
  snapshot/hash và dùng chung planner/runner. Snapshot v2 cũ tiếp tục validate.
- UI: POST tạo real job/tokenizer local; GET trang review theo job; manifest
  download; upload result từng JSON, giới hạn 1 MiB; save/approve theo revision
  và base result hash; export draft hoặc official chỉ khi toàn bộ chunk của job
  có revision hiện hành được duyệt. Tiến độ là số result import local, không phải
  runtime liveness. Notebook bootstrap app v2, mount Drive và chạy/resume file;
  Colab CLI orchestration chưa có.
- Main xác nhận tokenizer Qwen3.5 tải 6 files và load thành công; uv pip check
  đạt. Local fixture end-to-end với tokenizer thật + generation giả đạt: tạo
  2-chapter/3-chunk manifest, interrupt/resume, import đảo thứ tự + duplicate,
  giữ manual edit đến muộn, approve và official TXT; snapshot cũ byte-identical.
  GPU/model v2 và Drive interruption/resume chưa chạy. Main chạy full suite ngoài
  sandbox bằng `timeout 60s .venv/bin/python -m pytest -q`: 97 passed, 23
  subtests, 1 warning Starlette/httpx deprecation (12.15s). Schema khai báo tổng cộng 10 bảng (6 v1 + 4 bảng real mới),
  chưa kiểm tra DB người dùng/migration thực.
- Chưa làm: EPUB export/reader, glossary snapshot/editor, backup/restore, P2-03
  live Colab verify, P2-04 CLI orchestration và quality metrics report. Xem
  [REAL_BATCH](REAL_BATCH.md), [INTEGRATION](INTEGRATION.md), [schema](SQLITE_SCHEMA.md).

## User xác nhận kết quả chấm và chọn provider — 15/10/2026

- User xác nhận đã chấm và chọn `Qwen/Qwen3.5-4B` làm provider tích hợp; chọn
  chính xác Qwen3.5, model mới thêm gần nhất. Không cần hỏi/chờ chọn model nữa.
- Chưa có báo cáo/số đo được lưu trong repo. Không tự điền mức tiết kiệm 25%,
  18/18 chunks, đủ hai model hoặc zero critical errors; không tuyên bố formal
  phase P0 quality complete. `benchmarks/p0/criteria.json` còn `not_run` và
  `decision: null`, là artifact chưa cập nhật theo thông tin user.
- Mốc profile P0 trong [P0_MODELS](P0_MODELS.md): revision
  `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`, Transformers 5.3.0,
  accelerate 1.11.0, bitsandbytes 0.48.2, NF4 double quant fp16, SDPA, batch 1,
  budgets 768/2048/2048/4096, greedy seed 0, `enable_thinking=False`. Đây là
  cấu hình repo dùng làm mốc tích hợp, không phải số đo user vừa cung cấp.
- Đây là ảnh chụp trước khi hoàn tất UI/provider phía dưới; phần này hiện là
  lịch sử. Trạng thái mới nhất là mục “Offline pipeline Qwen3.5 và review v2”.

## Chuẩn bị tích hợp app/model P2/P3 — 15/10/2026

- Theo yêu cầu user, mở phạm vi chuẩn bị kỹ thuật và đánh giá readiness; chỉ cập
  nhật docs, không sửa app/runtime, không chạy GPU/model v2. Hợp đồng/thứ tự và
  task packets ở [INTEGRATION.md](INTEGRATION.md); roadmap chưa tick phase.
- Nền tảng v2 offline có thật; lúc ghi mục này profile/runtime/UI còn thiếu; xem
  mục mới nhất đầu file để biết phần đã triển khai sau đó. EPUB export vẫn thiếu. `criteria.json` còn `decision: null`
  do chưa cập nhật theo lựa chọn user; không phủ định xác nhận đã chấm/chọn.
- Kế hoạch bước đầu là profile v2 pinned Transformers 5.3/SDPA, mapping
  BatchEncoding, nested config/provenance, context/missing-key checks và
  `enable_thinking=false` được snapshot/hash; đã triển khai theo mục mới nhất.
- Main chạy trước baseline offline: 56 passed, 23 subtests passed (6 test files
  real bundles/runner/store, core, EPUB, Colab pipeline; 8.83s). Đây là kết quả
  của main, không phải kiểm thử runtime/model/Drive. Worker chỉ chạy
  `git diff --check` và rà link/claim tài liệu.
- Chưa chạy GPU/model v2, chưa kiểm tra Drive durability/checkpoint ngoài VM,
  chưa triển khai hay kiểm thử UI/revision v2; chưa lưu báo cáo/số đo P0 trong
  repo để xác nhận formal phase quality complete.

## Đồng bộ docs và dọn notebook — 15/10/2026

- Theo yêu cầu user, đồng bộ trạng thái P0, CLI và notebook Run all trong
  README, WORKFLOW, ROADMAP, P0_BENCHMARK, P0_MODELS và hướng dẫn Colab.
  Run all vẫn dùng được (`LIMIT=None` cho full), nhưng không chạy cùng script
  trên một kernel. P2 batch v2 vẫn offline; P0 script không thay P2-03/04.
- Lần đọc log gần nhất: `ch01-0001`, `ch01-0002`, `ch02-0000` đều EOS và đã
  lưu `technical_complete`; tổng 4/18, đang sinh `ch02-0001`. Tiến trình tool
  session `73353` vẫn chạy. Đây là quan sát theo thời điểm, không phải kết quả
  hoàn tất benchmark; không đọc/chấm bản dịch trước baseline.
- Dọn notebook local bằng backup nguyên bytes trước, refresh source nhúng,
  xóa outputs/execution counts; không can thiệp kernel đang chạy, nguồn/raw,
  checkpoint, SQLite hay sửa tay. Dữ liệu và auth CLI vẫn ở ngoài Git.
  Backup/readback/SHA tại `data/backups/notebooks/20261015T160043388408Z/`.
- Phạm vi commit gồm Qwen3.5/CLI/tests/docs đã kiểm chứng; không push.
  Full suite trước bước dọn: 92 passed, 23 subtests; sau dọn 29 test P0/CLI
  đạt, cả ba notebook JSON/source/syntax/config/clean-output đều đạt.
  Test CLI tùy chọn skip khi chưa cài extra `colab`. Các mục dưới là lịch sử.

## Qwen3.5 smoke thật đạt; script chạy qua CLI — 15/10/2026

- User yêu cầu worker sửa lỗi còn lại và tự động hóa. Hai worker `gpt-6-luna/low`
  phụ trách riêng runner/notebook và script; main tích hợp/kiểm chứng.
- Lỗi mới là guard revision sau tải weights: TextConfig nested không giữ
  `_commit_hash`. Runner resolve `config.json` tại revision pin, kiểm SHA từ
  cache snapshot; hash model nếu có vẫn phải khớp, không bỏ kiểm provenance.
  Snapshot/config/output cũ giữ nguyên. Notebook Qwen3.5 backup bytes trước
  refresh bootstrap; checkpoint/session lỗi cũ không bị ghi đè.
- Worker restart đúng kernel trên runtime T4 hiện có, không cấp VM mới;
  smoke `ch01-0000` đạt `technical_complete`, 830 input / 922 output tokens,
  EOS, error null. Session ghi đúng SHA `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`,
  load khoảng 34,29 giây. Chưa đọc/chấm nội dung bản dịch.
- Có `scripts/run_p0_colab.py`: xác minh assignment/kernel đang idle, kiểm pins,
  GPU/Drive, bootstrap source hiện tại, reload runner, snapshot và chạy toàn
  bộ chunk thiếu. `--limit 1` cho smoke; `--restart-kernel` restart cùng kernel.
  Dừng khi lỗi/needs_review, không tạo VM hoặc tự retry generation.
  Xem [COLAB_AUTOMATION.md](COLAB_AUTOMATION.md).
- Main chạy full suite ngoài sandbox: 92 passed, 23 subtests passed, một warning
  Starlette/httpx có sẵn. Script `--dry-run`, syntax và `git diff --check` đạt.
  Main đã khởi chạy script full với `--restart-kernel` để resume sau chunk đầu;
  runtime PID 9472, nạp model 58,4 giây, xác minh resume `1/18` và đang sinh
  `ch01-0001`. Tiến trình local tool session `73353` còn chạy để nhận log;
  chưa kết luận đủ 18 chunk, không coi smoke là benchmark/go-no-go.

## Sửa BatchEncoding Qwen3.5 qua CLI — 15/10/2026

- User đã đăng nhập CLI và yêu cầu sửa block cuối Qwen3.5. Lỗi gốc là
  `BatchEncoding is not JSON serializable` tại `build_plan -> digest(ids)`,
  trước tải weights. Transformers 5.3 trả mapping mặc định; runner giờ lấy
  `input_ids` từ mapping, giữ tokenizer trả list. Không đổi model/config.
- Worker thêm regression count/hash, backup nguyên bytes notebook tại
  `data/backups/notebooks/20261015T153001422766Z/`, đọc lại byte-equal; chỉ refresh
  bootstrap Qwen3.5. Giữ output lỗi và hai notebook cũ. Test bootstrap tách
  source khỏi execution count; notebook cũ kiểm source nhúng/checksum riêng.
- Main dùng CLI đọc Jupyter sessions của runtime T4 đang có, xác định đúng
  notebook Qwen3.5/kernel idle, ghi alias `qwen35-vscode` vào state repo.
  Không cấp VM/kernel mới. Qua `colab exec`, backup runner remote, cập nhật và
  reload trong kernel PID 752; chạy tokenizer thật từ cache revision đã pin.
- Kiểm thật: trả `BatchEncoding`, normalize thành list token, plan đủ 5 chương /
  18 chunk, budget/hash từng chunk và canonical JSON đều đạt. Main chạy 20 test
  P0 đạt, `git diff --check` đạt. Chưa nạp weights/chạy lại block sinh, chưa kiểm
  VRAM, tốc độ hoặc chất lượng. Kernel hiện tại đã nhận bản sửa; lần chạy block
  cuối tiếp theo dùng runner mới. Output lỗi cũ vẫn là lịch sử.

## Gộp Colab CLI vào .venv — 15/10/2026

- Theo yêu cầu mới, `google-colab-cli==0.7.4` đã chuyển vào `.venv` Python 3.12
  chung với ứng dụng. Extra `colab` trong `pyproject.toml` ghi dependency;
  cài lại bằng `uv pip install --python .venv/bin/python -e '.[test,colab]'`.
  CLI cần Python 3.12+, ứng dụng riêng vẫn hỗ trợ 3.11.
- `scripts/colab` gọi `.venv/bin/colab`, giữ state tại `data/colab-cli/`.
  Đã dọn môi trường `.tools/colab` và launcher global cũ đã xác minh đúng target.
  Auth/log vẫn theo mặc định `~/.config/colab-cli/`; xem [COLAB_CLI.md](COLAB_CLI.md).
- Không nâng dependency ứng dụng trong lần cài. `uv pip check`, version/help,
  restart-kernel help và shell syntax đạt. Chưa đăng nhập hoặc restart kernel.
- Main chạy full suite ngoài sandbox: 81 passed, 23 subtests passed, 1 failure
  ở test portable Qwen3.5 do bootstrap cell hiện có `execution_count=3` thay
  vì `None`; giữ notebook người dùng đang chạy. Lượt trong sandbox timeout
  45 giây ở nhóm web. Không claim toàn bộ suite đạt.

## Cài Colab CLI riêng — 15/10/2026

- Theo yêu cầu người dùng, cài `google-colab-cli==0.7.4` vào
  `.tools/colab/google-colab-cli`, thêm executable `scripts/colab` và ignore
  `/.tools/colab/`. Giữ `.venv` ứng dụng riêng. `uv` còn tạo launcher
  `~/.local/bin/colab` trỏ bản cài trong repo.
- Wrapper giữ session metadata dưới `data/colab-cli/`; auth/log của CLI dùng
  mặc định `~/.config/colab-cli/`. Xem [COLAB_CLI.md](COLAB_CLI.md).
- Đã kiểm version/help/restart-kernel help/shell syntax và ignore paths.
  Chưa đăng nhập, cấp runtime hoặc restart. Cần user hoàn tất OAuth qua terminal
  và xác định đúng kernel; runtime VS Code chưa có metadata CLI có thể hiện `[?]`,
  không được đoán kernel để restart. Google Colab extension VS Code 0.9.7 đã có.

## Thêm notebook Qwen3.5-4B — 15/10/2026

- Theo yêu cầu người dùng, thêm `notebooks/p0_qwen35_benchmark.ipynb` bên cạnh
  hai notebook cũ. Model `Qwen/Qwen3.5-4B`, pin revision
  `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`; Transformers 5.3.0,
  accelerate 1.11.0, bitsandbytes 0.48.2. Chi tiết/nguồn ở [P0_MODELS.md](P0_MODELS.md).
- Colab Free/T4: text-only `Qwen3_5ForCausalLM`, NF4/double quant, float16,
  SDPA, batch 1, source/input/output/context = 768/2048/2048/4096, greedy,
  seed 0, tắt thinking trong template và snapshot. Loader ánh xạ text weights,
  kiểm loading info/context/revision trước sinh. Không nạp vision model.
- Corpus mặc định `MyDrive/p0/corpus.json`, `LIMIT=1` thử một chunk;
  đổi `None` để resume toàn bộ. Mỗi model dùng runtime riêng; kết quả Qwen3.5
  nằm trong `runs/Qwen3.5-4B-<snapshot>`. Giữ baseline trước đọc output.
  Không tự tăng trần GPU đã chốt, chưa upload notebook mới lên Drive.
- Builder refresh bootstrap cả ba notebook, giữ model/config hai bản cũ;
  notebook mới dùng progress/OOM guard có sẵn. Main kiểm 46 test P0 + real
  bundles/runner đạt; cả ba notebook khớp source nhúng, syntax hợp lệ, không
  outputs/execution counts. Chưa cài stack GPU, chạy Colab/model/tokenizer thật,
  đo VRAM/tốc độ/chất lượng hoặc kiểm reconnect Drive thật.

## P0 hiện tại và notebook đã làm sạch — 15/10/2026

- Chưa có benchmark hoàn tất hoặc quyết định go/no-go. Các lượt Qwen2.5 trước
  dừng ở chunk đầu do output `max_tokens`/lặp; lần cấu hình FP32 sau đó OOM ngay
  lúc nạp model. Chưa có căn cứ nói cấu hình đã hết lỗi.
- Bước tiếp theo là chờ người dùng xác nhận baseline dịch tay hoàn tất và cung
  cấp bằng chứng lượt chạy. Chưa đọc/chấm output trước baseline; không mở thêm
  phiên GPU hoặc dùng thêm ngân sách nếu chưa có quyết định riêng.
- P2 batch v2 hiện chỉ được kiểm offline bằng synthetic tokenizer/generation.
  Sau khi cổng P0 được người dùng xử lý, cần xác minh tokenizer/model và luồng
  Colab thực theo ngân sách đã chốt. UI review/export, EPUB export và điều phối
  Colab vẫn để sau.
- Trước khi dọn notebook, đã lưu nguyên bytes hai bản gốc trong Git-ignore tại
  `data/backups/notebooks/20261015T145723236754Z/`; `verification.json` ghi SHA-256
  và bản sao đã được đọc lại so byte-for-byte. Hai notebook tracked được refresh
  bootstrap từ source hiện tại, đặt execution count về `null`, xóa outputs và
  Colab provenance; giữ model/config/prompt/generation code, `p0_bootstrap`, GPU
  và kernel metadata. Không sửa kernel đang chạy, upload Drive hay xem output.
- Kiểm notebook P0: JSON, source nhúng, syntax/flow bootstrap và outputs sạch đạt;
  `.venv/bin/python -m pytest -q tests/test_p0.py tests/test_p0_progress.py` —
  17 passed. Refresh đã sửa mismatch Qwen3 bootstrap được thấy ở kiểm tra trước.
- Main chạy lại toàn bộ suite sau khi làm sạch: `timeout 60s .venv/bin/python
  -m pytest -q` ngoài sandbox — 80 passed, 23 subtests passed trong 10,07 giây;
  còn một cảnh báo deprecation Starlette/httpx, không có failure. `git diff
  --check` đạt. Không commit dữ liệu local, DB hoặc output notebook.
- Worker staging hiện chọn `gpt-6-luna`, reasoning `low`, đồng bộ với AGENTS.md;
  chưa cài hoặc kích hoạt cấu hình runtime.

## P2 offline: batch thật v2 và Store local — 15/10/2026

Mục này là trạng thái tại thời điểm ghi; phần “ba bảng/chưa có UI” bên dưới đã
được cập nhật bởi mục “Offline pipeline Qwen3.5 và review v2” đầu file.

- Có `app/real_bundles.py` v2 với planner tokenizer, manifest snapshot bất biến,
  provenance pinned model/tokenizer và result chỉ nhận status completed/EOS;
  `app/real_runner.py` chạy file-only, lưu một result JSON mỗi chunk, resume từ
  checkpoint đã validate. Đây là mã kiểm thử offline, không phải bằng chứng model
  đã chạy.
- Tại thời điểm mục lịch sử này, `Store` có ba bảng additive `real_jobs`, `real_chunks`, `real_results`, thư mục
  `real-batches/` và `real-results/`; v1 fake tables, UI/latest fake job và manual
  revisions được giữ riêng. Import kiểm source/chapter hiện tại, checksum,
  provenance, duplicate/conflict, và có file-first recovery sau transaction crash.
- `scripts/real_batch.py` có export/import/status. Export dùng tokenizer-only
  snapshot theo revision pin, không tải weights; CLI báo `transformers==4.57.3`
  nếu thiếu package. Hướng dẫn thao tác ở [REAL_BATCH.md](REAL_BATCH.md).
- Database thật chỉ được main kiểm tra ở chế độ SQLite `mode=ro`; chưa migrate
  hoặc ghi DB thật. `Store.__init__` sẽ tạo ba bảng bằng `CREATE TABLE IF NOT
  EXISTS` lần mở kế tiếp. Không chạy GPU, tải model hay upload Drive. P0 JSON chưa
  có adapter sang v2; kết quả v2 chưa xuất hiện trong UI review/export. EPUB
  export vẫn chưa có.
- Test synthetic tokenizer/generation và CLI guard: `.venv/bin/python -m pytest
  -q tests/test_real_store.py tests/test_core.py tests/test_epub.py` — 20 passed,
  23 subtests passed. Chưa xác minh network/tokenizer thật, CUDA/VRAM/quota, Colab,
  Drive sync durability, model output hoặc chất lượng dịch.
- Main chạy cả suite: 79 passed, 23 subtests, 1 failure và 1 warning. Cả 33 test
  P2 mới đều đạt; failure duy nhất là `P0Tests.test_portable_notebook_bootstrap_matches_sources_and_runs_offline`,
  mismatch notebook Qwen3 đã có trước thay đổi này. Main xác nhận checksum
  notebook Qwen3 không đổi; checksum notebook Qwen2.5 đổi trong phiên do thay đổi
  bên ngoài, không do worker/main. Chỉ metadata execution/output type được đọc,
  không đọc bản dịch. `py_compile`, CLI `--help`, `git diff --check` đều đạt.
- [SQLITE_SCHEMA.md](SQLITE_SCHEMA.md), [ROADMAP.md](ROADMAP.md),
  [EPUB_IMPORT.md](EPUB_IMPORT.md) và README có giới hạn và trạng thái hiện tại.

# Lịch sử — 14/10/2026 (Asia/Bangkok)

Đọc sau WORKFLOW; đây là trạng thái vận hành, không thay PLAN/ROADMAP.

## Qwen2.5 OOM khi tải FP32 — 14/10/2026

- Notebook người dùng gửi có `OutOfMemoryError` ngay trong `from_pretrained`,
  trước sinh chunk. Snapshot `a22f53e644544c0e85dde20dca821b8388b175ec25700bc5cd4c545501b1a0e5`
  vẫn NF4, compute/load FP32. Cần thêm 2,03 GiB khi GPU T4 14,56 GiB chỉ còn
  1,81 GiB; log ghi PID 15033 dùng 6,85 GiB và process hiện tại dùng 5,91 GiB.
- User xác nhận chỉ chạy Qwen2.5. Chưa xác định process kia thuộc kernel cũ
  hay tiến trình nào; không quy cho Qwen3, không tự kill. Đây là OOM tải model,
  chưa có bằng chứng FP32 đã hết lỗi lặp. Không suy ra ngưỡng VRAM an toàn từ
  một allocation thất bại, không tự tăng ngân sách/đổi model/precision lần nữa.
- Notebook thêm log PID/VRAM trước load và hướng xử lý OOM: ngắt kernel cũ,
  Colab `Runtime -> Disconnect and delete runtime`, kết nối phiên GPU mới.
  Tạo lại VM không xóa corpus/checkpoint trên Drive; giữ cùng snapshot để resume.
  Chỉ rerun cell có thể còn giữ process/model cũ. Không tự chạy GPU thêm.
- Kiểm offline: 27 passed, 1 deselected (test Qwen3 notebook/source đang giữ
  nguyên từ phiên trước). Mock OOM kiểm thông báo, exception cause, log PID/VRAM
  và phục hồi globals; Qwen2.5 syntax/bootstrap khớp source, không output lưu.


## Qwen2.5 vẫn lặp sau phạt lặp — 14/10/2026

- Lượt sau dùng snapshot `ad12f324e4fb8ca3e92e2b7950e2cb29085b7ad34071d69c647625171222d3a8`
  vẫn dừng ở `ch01-0000`: 826 input / 2.048 output tokens, `max_tokens`,
  `needs_review`, không exception generation. Đọc checkpoint Drive: 2.012 token
  có ID 0, 16 token cuối toàn ID 0. Phạt lặp 1.1 không giải quyết được lỗi.
- Đối chiếu [Qwen troubleshooting](https://qwen.readthedocs.io/en/v2.0/inference/chat.html#troubleshooting):
  cảnh báo float16 có thể gây mất ổn định số và lặp dấu chấm than. Đây là căn cứ
  cho hướng sửa, chưa có logits/GPU để chứng minh nguyên nhân numerical.
- Bản sửa Qwen2.5 bỏ phạt lặp thêm ở lượt trước, chuyển compute và các phần
  không lượng tử sang float32; weights vẫn NF4 4-bit. Runner dùng precision
  từ config thay vì hardcode fp16, snapshot/plan lưu cấu hình mới. Qwen3 giữ
  mặc định fp16 và notebook đang chạy giữ nguyên.
- Chưa chạy GPU cấu hình mới. Hai lượt Qwen2.5 đã dùng hết trần cũ; không tự
  khởi chạy lượt thứ ba hay coi test offline là bằng chứng model hết lỗi.
- Main kiểm 26 test offline đạt, 1 test Qwen3 bỏ riêng: notebook Qwen3 giữ
  source runner cũ và execution count khi đang chạy, nên không bằng refresh
  source mới. Qwen2.5 syntax/bootstrap/readback đạt; mock test xác nhận dtype
  fp16/fp32 truyền đúng cho quantizer/model load và snapshot/plan đổi.


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

Đây là quyết định/giới hạn lịch sử trước yêu cầu mở P2 và xác nhận provider ngày
15/10/2026; xem các mục mới nhất đầu file. P1 local fake có bằng chứng trong
P1.md; benchmark full/quality gate vẫn cần phân biệt với xác nhận user.

## Đã chốt và còn mở

- EN → VI, ngân sách 0 đồng, Colab free theo phiên tương tác; người dùng tự review.
- Các ứng viên P0 ban đầu là Qwen3-4B-Instruct-2507 và Qwen2.5-7B-Instruct;
  user hiện đã chọn Qwen3.5 cho tích hợp. Revision/pins lịch sử ở
  [P0_MODELS.md](P0_MODELS.md); không đổi cấu hình đã pin âm thầm.
- Benchmark chính thức: 5 chương × 2 model, không bỏ đoạn, mọi chunk hoàn tất,
  zero critical sau review, tổng thời gian sinh + sửa giảm ≥25% so baseline.
- Người dùng chốt ngày 14/10/2026: tiếng Việt tự nhiên, giữ giọng nhân vật và
  tên riêng; tối đa 2 lần thử/model, tổng 4 phiên Colab miễn phí. Đã ghi
  [criteria.json](../benchmarks/p0/criteria.json); lịch sử chuẩn bị benchmark
  bên dưới không phản ánh xác nhận chấm/chọn mới nhất ngày 15/10/2026.
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
