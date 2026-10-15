# Batch dịch thật v2: local → Colab → local

Đây là luồng Qwen3.5 v2 giữa app/`Store` local, file trên Google Drive và
notebook Colab; SQLite chỉ nằm local. UI local tạo job, nhận result và review/
duyệt; notebook là thao tác thủ công/resumable. Main đã xác minh local fixture
end-to-end bằng tokenizer Qwen3.5 thật và generation giả. Main chạy full suite
 ngoài sandbox: `timeout 60s .venv/bin/python -m pytest -q` đạt 97 passed, 23
 subtests, 1 warning Starlette/httpx deprecation (12.15s). Chưa chạy model/GPU
v2, và chưa xác minh độ bền Drive qua ngắt/resume.
Colab CLI orchestration v2 chưa hoàn tất.

## 1. Xuất manifest ở máy local

Ở trang sách chọn **Tạo job Qwen3.5**. Backend local tải tokenizer/config pin và
đóng băng manifest v2 trong `real_jobs`/`real_chunks`; không tải model weights.
Extra ứng dụng là `tokenizer` (`transformers==5.3.0`). Profile Qwen3.5 dùng revision
`851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`, SDPA, NF4 double quant/fp16,
batch 1, greedy seed 0 và chat template `enable_thinking=false`. Giới hạn token
source/input/output/context là 768/2048/2048/4096. Snapshot v2 cũ vẫn được
validate; kết quả P0 không cùng schema và không import sang v2.

```bash
.venv/bin/python scripts/real_batch.py export \
  --data-dir data \
  --book-id '<BOOK_UUID>' \
  --model Qwen/Qwen3.5-4B \
  --revision 851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a \
  --output /tmp/novel-batch/manifest.json
```

Lệnh CLI trên dành cho local batch scripting; luồng UI không cần tự chạy lệnh này.
Lệnh tạo job bất biến trong
SQLite, bản manifest trong `data/real-batches/<JOB_UUID>.json` và bản trao đổi ở
đường dẫn `--output`. Không chọn lại đường dẫn output đã tồn tại. Nếu lỗi xảy ra
sau khi job được lưu, có thể lấy manifest chuẩn từ DB bằng `Store.get_real_manifest`
hoặc file `real-batches`.

Job lưu source text, source offsets, token IDs, tokenizer/template, prompt,
snapshot model, ngân sách và hashes. Chunk nhắm 768 source tokens; toàn bộ chat
input tối đa 2.048 tokens, dành 2.048 tokens cho output trong budget 4.096.
Glossary đang rỗng revision 0 và context là `none`. Manifest và mỗi result có
giới hạn 16 MiB. Bundle được tạo từ toàn bộ source/chapter hiện tại; sửa source
hoặc mapping chapter sẽ khiến import bị từ chối.

CLI resolve tokenizer snapshot ở revision pin rồi nạp từ thư mục local, không
dựa vào `tokenizer.init_kwargs` để nhận diện commit. `chat_template_kwargs` là
một phần snapshot/hash và planner/runner cùng dùng `enable_thinking=false`.
Bundle vẫn giữ tương thích các snapshot v2 cũ. Hub tải có lọc file bằng
[`snapshot_download(allow_patterns=...)`](https://huggingface.co/docs/huggingface_hub/v1.24.0/en/package_reference/file_download),
còn [`AutoTokenizer.from_pretrained`](https://huggingface.co/docs/transformers/en/model_doc/auto)
nhận đường dẫn local/revision; mã đặt `trust_remote_code=False`.

## 2. Chạy notebook trên Colab (fallback thủ công)

Ở trang real job tải manifest và notebook. Tạo thư mục Drive cho job và upload
manifest JSON vào đó (manifest chứa chunk source cần dịch; không upload raw TXT/
EPUB hay SQLite). Mở notebook trên Colab, cấp runtime GPU, sửa `MANIFEST` và `OUTPUT` trong
cell cấu hình thành hai đường dẫn theo job rồi chạy các cell từ đầu. Notebook
bootstrap mã runner v2 có checksum, cài `transformers==5.3.0`,
`accelerate==1.11.0`, `bitsandbytes==0.48.2`, mount Drive rồi chạy runner.
Rerun cùng manifest/output để resume checkpoint đã validate; file result ghi từng
chunk EOS. Không đưa `library.sqlite3`, thư mục `data/`, raw TXT/EPUB hoặc secrets
lên Drive/Colab. Notebook không truy cập DB và không tự truyền result về app.

```bash
python -m pip install 'transformers==5.3.0' 'accelerate==1.11.0' 'bitsandbytes==0.48.2'
python -m app.real_runner \
  /content/drive/MyDrive/novel-batch/<job>/manifest.json \
  /content/drive/MyDrive/novel-batch/<job>/results
```

Runner nạp revision Qwen3.5 bằng loader text-only và SDPA; đòi CUDA, kiểm
tokenizer/template/snapshot và ghi mỗi EOS result riêng. Trên Drive, runner
yêu cầu output nằm dưới mounted `MyDrive`. Nếu runtime dừng, chạy lại cùng
notebook/manifest/output. Đây là fallback thủ công, không phải Colab CLI orchestration.
Runtime/Drive thật chưa được xác minh end-to-end.

## 3. Nhập và review trên app local

Sau khi notebook hoàn tất hoặc có checkpoint cần review, tải/copy từng result
JSON từ Drive về máy local. Trong trang job, upload từng file ở form (giới hạn
UI 1 MiB/file). App kiểm job ID, manifest/input hash, provenance, checksum và
EOS trước khi ghi result. Có thể chạy `scripts/real_batch.py import` để nhập
ngoài UI; mỗi lần một result. Cùng checksum là `duplicate`; payload khác cùng
job/chunk là conflict, result cũ được giữ.

```bash
.venv/bin/python scripts/real_batch.py import --data-dir data \
  --result /tmp/novel-batch/results/<CHUNK_UUID>.json
.venv/bin/python scripts/real_batch.py status --data-dir data --job-id '<JOB_UUID>'
```

Import kiểm tra schema v2, job/manifest/input hash, provenance, checksum, trạng
thái EOS và source/chapter hiện tại. Mỗi result được lưu file dưới
`data/real-results/<JOB_UUID>/` rồi commit cùng transaction SQLite. Nếu process
dừng sau khi file bền vững nhưng trước commit, nhập lại file sẽ hoàn tất. Input
bị từ chối nhỏ hơn 16 MiB được giữ ở `data/real-results/rejected/` để chẩn đoán;
các file này có thể chứa văn bản truyện. Lệnh `status` chỉ in trạng thái và số
chunk, không in source/result text. Review UI ở `/books/<BOOK_ID>/real-jobs/<JOB_ID>`
giữ revision theo `(job_id, chunk_id)` trong `real_revisions`. Lưu và duyệt là
thao tác riêng; optimistic check dùng base revision/result hash. Result tới muộn
không thay bản sửa đã lưu. TXT export nằm theo job và thứ tự chapter/chunk trong
manifest: `?draft=true` đánh dấu thiếu/chưa duyệt; official yêu cầu mọi chunk có
revision hiện hành đã duyệt. Progress là số result đã nhập local, không phải dấu
hiệu runtime đang chạy.

## Ranh giới hiện tại

- UI giữ luồng fake v1 riêng và có trang review v2 theo job. TXT export v2 dùng
  job được chọn rõ, không lẫn revision hoặc selection với v1.
- `real_chunks` lưu segmentation riêng theo tokenizer. Import không reanchor
  segmentation sang `chunks` P1 và không áp dụng/ghi đè revision.
- P0 notebook có plan/session/result schema riêng, chưa có adapter sang v2.
- Chỉ snapshot EN → VI, model/revision được hỗ trợ, glossary/context rỗng và EOS
  completion được nhận. P0 result schema không import sang v2. Chưa có EPUB
  export, glossary snapshot/editor, backup/restore, hoặc Colab CLI orchestration.
- Local fixture dùng tokenizer thật + generation giả đã kiểm tra manifest,
  resume, import/idempotency, late edit, approval và official TXT. GPU/model v2
  và Colab checkpoint ngắt/resume chưa được kiểm chứng trên tài khoản thật.
  Không claim chất lượng từ runner/integration.
- Fixture dùng generation giả; không chứng minh inference model, GPU, mạng, auth,
  VRAM, quota, độ bền Drive hoặc chất lượng đầu ra hoạt động.
