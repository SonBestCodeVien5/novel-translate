# Batch dịch thật v2: local → Colab → local

Đây là luồng file offline giữa `Store` local và runner v2; SQLite chỉ nằm trên
máy local. Luồng không dùng dữ liệu hay schema checkpoint P0, không kết nối UI,
Drive API hoặc Colab CLI tự động. Chưa chạy model/GPU hoặc xác minh độ bền file
trên Drive thật.

## 1. Xuất manifest ở máy local

Đảm bảo model đã được người dùng chọn và tokenizer truy cập được. CLI chỉ tải
tokenizer tại revision cố định, không tải weights. Bản hiện hỗ trợ hai model pin
trong `app/real_bundles.py`; Transformers cần `4.57.3`.

```bash
.venv/bin/python -m pip install 'transformers==4.57.3'
.venv/bin/python scripts/real_batch.py export \
  --data-dir data \
  --book-id '<BOOK_UUID>' \
  --model Qwen/Qwen2.5-7B-Instruct \
  --revision a09a35458c702b33eeacc393d103063234e8bc28 \
  --output /tmp/novel-batch/manifest.json
```

Thay model/revision bằng cặp Qwen3 đã pin nếu cần. Lệnh tạo job bất biến trong
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
dựa vào `tokenizer.init_kwargs` để nhận diện commit; Transformers 4.57.3 không
luôn đưa `_commit_hash` vào trường đó ([source Transformers 4.57.3](https://github.com/huggingface/transformers/blob/v4.57.3/src/transformers/tokenization_utils_base.py#L2057-L2151)).
Hub hỗ trợ tải có lọc file bằng
[`snapshot_download(allow_patterns=...)`](https://huggingface.co/docs/huggingface_hub/v1.24.0/en/package_reference/file_download),
còn [`AutoTokenizer.from_pretrained`](https://huggingface.co/docs/transformers/en/model_doc/auto)
nhận đường dẫn local/revision; mã đặt `trust_remote_code=False`.

## 2. Chạy file-only trên Colab

Chỉ sao chép `manifest.json` và mã runner cần thiết:
`app/__init__.py`, `app/bundles.py`, `app/real_bundles.py`, `app/real_runner.py`.
Không sao chép `library.sqlite3`, `data/`, raw EPUB/TXT hoặc secrets. Đặt mã
trong `MyDrive/novel-batch/code/app/` và manifest trong thư mục job trên Drive
đã mount. Trên Colab GPU, cài đúng
pins của notebook P0 rồi chạy:

```bash
python -m pip install 'transformers==4.57.3' 'accelerate==1.11.0' 'bitsandbytes==0.48.2'
PYTHONPATH=/content/drive/MyDrive/novel-batch/code python -m app.real_runner \
  /content/drive/MyDrive/novel-batch/manifest.json \
  /content/drive/MyDrive/novel-batch/results
```

Runner nạp đúng revision, yêu cầu CUDA, so template và input IDs với manifest,
chạy tuần tự và ghi một file JSON cho mỗi chunk đã kết thúc bằng EOS. Nếu runtime
dừng, chạy lại cùng manifest và thư mục results; runner kiểm tra checkpoint rồi
bỏ qua result hợp lệ. Output không hoàn tất được giữ trong `results/failed/` và
không được nhập vào Store. Đây là hướng dẫn thao tác, chưa phải kiểm chứng cài
đặt, quota, VRAM, thời lượng hoặc Drive durability trên tài khoản Colab.
Các lệnh mẫu là hướng dẫn; cập nhật này không chạy GPU và không đổi notebook P0
đang có.

## 3. Nhập từng result về local

Tải/copy các file result JSON về máy local; không tải database. Mỗi lệnh nhập một
result. Có thể chạy lại sau lỗi hoặc restart: cùng checksum trả `duplicate`,
payload khác cho cùng job/chunk trả conflict và giữ result đã lưu.

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
chunk, không in source/result text.

## Ranh giới hiện tại

- P1 UI và `get_book` chỉ đọc job/result fake v1. Job/result v2 không xuất hiện
  trong review hay TXT export, và không đổi các manual revision v1.
- `real_chunks` lưu segmentation riêng theo tokenizer. Import không reanchor
  segmentation sang `chunks` P1 và không áp dụng/ghi đè revision.
- P0 notebook có plan/session/result schema riêng, chưa có adapter sang v2.
- Chỉ snapshot EN → VI, hai revision pin, glossary/context rỗng và EOS completion
  được nhận. Chưa có EPUB export, UI/provider buttons, Drive API, tự động điều
  phối Colab hay chứng nhận chất lượng dịch.
- Test dùng tokenizer/generation giả; không chứng minh model, GPU, mạng, auth,
  VRAM, quota, độ bền Drive hoặc chất lượng đầu ra hoạt động.
