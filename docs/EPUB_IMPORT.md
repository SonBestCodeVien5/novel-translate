# Nhập EPUB local và luồng Colab

Phạm vi nhập EPUB được mở ngày 14/10/2026. Sau đó có thêm batch v2 offline local
cho TXT/EPUB source rows, nhưng EPUB chưa được chạy qua tokenizer/model thật.
Provider đã chọn là Qwen3.5; benchmark cũ được lưu tại
[archive/p0](../archive/p0/README.md). Có [EPUB export](EPUB_EXPORT.md) theo profile
mapping bảo toàn và [script Colab v2](COLAB_V2.md) trên phiên đã đăng ký.

## Chạy import

```bash
.venv/bin/python scripts/import_epub.py 'data/Reformat...at_Noble.epub' --data-dir data
```

Có thể thêm `--title 'Tên sách'`; mặc định lấy tiêu đề từ metadata EPUB.
Script in book ID, số source unit/chunk, không tạo translation job. Nhập cùng raw,
parser version và cặp ngôn ngữ trả lại book đã có, giữ sửa tay. Cùng tên khác raw
là sách mới. Trang chủ nhận EPUB tối đa 64 MiB, tên trống lấy metadata;
sách nhập bằng UI hoặc CLI có thể review
trong app local và tạo real job Qwen3.5, nhập/review kết quả rồi xuất TXT theo job.

Raw lưu tại `data/sources/<rawsha>.epub`, mapping tại
`data/sources/<rawsha>.epub-spine-1.mapping.json`; DB ở `data/library.sqlite3`.
Mapping giữ spine ordinal, chapter ordinal (null cho image-only), locator XHTML,
source hash, text nodes/tails và block offsets. Đừng chỉnh raw/mapping trực tiếp.
Ảnh-only không tạo chapter text rỗng; unit vẫn được giữ trong mapping/EPUB.

Parser chỉ đọc archive, không extract/fetch/execute. Giới hạn raw64MiB, expanded
128MiB, mỗi entry8MiB,10000 entries,ratio200; từ chối path unsafe, duplicates,
symlink, encryption, internal DTD/entity, XML/spine/resource không hỗ trợ.
DOCTYPE XHTML external thông thường được nhận; parser không fetch DTD.

## Dữ liệu

File EPUB gốc giữ nguyên bytes trong thư mục sources local; SQLite lưu chương/text
đã parse theo thứ tự spine, cùng locator/mapping để truy ngược XHTML. Tài nguyên
ảnh/link/metadata còn trong EPUB gốc. Mỗi mục XHTML spine là một đơn vị nguồn ban
đầu, có thể gồm cả bìa/giới thiệu; chưa tự đoán nhiều chương trong một XHTML.

## Luồng file hiện có

```text
EPUB local → backend parse spine → SQLite local + raw EPUB/mapping
                                  ↓ real_batch export
                         local SQLite + manifest v2
                                  ↓ copy manifest + runner code (thủ công)
                         Colab file runner → result JSON/chunk
                                  ↓ copy result files (thủ công)
                         real_batch import → local SQLite
```

SQLite chỉ do backend local truy cập. Không upload database lên Drive hoặc mở nó
trong Colab. Batch v2 gồm ID/thứ tự, source text/hash, input IDs, prompt/glossary/
config và model/tokenizer revision; result phải khớp batch, provenance và EOS
trước khi nhập. Import trùng là no-op; kết quả xung đột hoặc lệch source/snapshot
bị từ chối. P1 manual revisions được giữ riêng; kết quả v2 có trang review,
duyệt và TXT draft/official theo job, không tự chuyển sửa tay P1 sang v2.

Runner lưu từng result ra thư mục output trước khi tiếp tục. Có thể dùng thư mục
Drive làm checkpoint ngoài VM, nhưng cách mount/copy và độ bền Drive chưa kiểm
chứng. Mất phiên thì người dùng chạy lại cùng manifest/output; runner kiểm
checkpoint hợp lệ, bỏ qua result đã lưu và dịch lại chunk dở.

## Giới hạn đã biết

Offline P2 có bundle v2, planner tokenizer, runner file-only, Store local và CLI
export/import/status và UI review. Fixture local đã kiểm tokenizer Qwen3.5 thật
với generation giả; chưa chạy model/GPU v2 hoặc kiểm checkpoint Drive qua ngắt/
resume trên tài khoản người dùng. Chưa kiểm VRAM, thời gian hoặc độ bền sync.

Notebook `notebooks/translate.ipynb` dùng manifest v2 từ app, được tải ở trang
sách/job. Notebook P0 lưu trữ có schema riêng và không import sang v2.
CLI `real_batch.py` không tạo phiên Colab, mount Drive hoặc tự chuyển file.
Xem [hướng dẫn batch v2](REAL_BATCH.md).

Colab CLI có extra/wrapper và script v2. Bằng chứng runtime mới nhất ở HANDOFF;
không coi test offline là bằng chứng GPU hoặc Drive durability.
