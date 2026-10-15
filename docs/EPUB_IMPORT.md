# Nhập EPUB local và luồng Colab

Phạm vi nhập EPUB được mở ngày 14/10/2026. Sau đó có thêm batch v2 offline local
cho TXT/EPUB source rows, nhưng EPUB chưa được chạy qua tokenizer/model thật.
Không thay notebook P0; chưa có EPUB export hay điều phối Colab tự động. Chưa có
kết quả go/no-go P0.

## Chạy import

```bash
.venv/bin/python scripts/import_epub.py 'data/Reformat...at_Noble.epub' --data-dir data
```

Có thể thêm `--title 'Tên sách'`; mặc định lấy tiêu đề từ metadata EPUB.
Script in book ID, số source unit/chunk, không tạo translation job. Nhập cùng raw,
parser version và cặp ngôn ngữ trả lại book đã có, giữ sửa tay. Cùng tên khác raw
là sách mới. Giao diện upload vẫn chỉ nhận TXT; sách nhập bằng CLI có thể review
trong app local nhưng job hiện vẫn là fake provider.

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
bị từ chối. P1 manual revisions vẫn được giữ, nhưng kết quả v2 chưa được chiếu
vào UI review hay export.

Runner lưu từng result ra thư mục output trước khi tiếp tục. Có thể dùng thư mục
Drive làm checkpoint ngoài VM, nhưng cách mount/copy và độ bền Drive chưa kiểm
chứng. Mất phiên thì người dùng chạy lại cùng manifest/output; runner kiểm
checkpoint hợp lệ, bỏ qua result đã lưu và dịch lại chunk dở.

## Giới hạn đã biết

Offline P2 có bundle v2, planner tokenizer, runner file-only, Store local và CLI
export/import/status. Kiểm thử dùng tokenizer/generation giả. Chưa chạy tokenizer
thật, tải weights, GPU, Drive hoặc Colab trên tài khoản người dùng; chưa kiểm auth,
quota, VRAM, thời gian hoặc độ bền sync.

Notebook P0 hiện là runner benchmark riêng; corpus/results của nó chưa cùng schema
bundle v2 và chưa có adapter vào SQLite. CLI `real_batch.py` không tạo phiên Colab,
mount Drive hoặc tự chuyển file. UI P1 vẫn chỉ xử lý fake provider; kết quả v2
chưa có flow review/export chính thức. Xem [hướng dẫn batch v2](REAL_BATCH.md).

[Colab CLI chính thức](https://github.com/googlecolab/google-colab-cli) chưa được
cài hay kiểm chứng trên WSL/tài khoản người dùng (P2-03). P2-04 tự động điều phối
vẫn phụ thuộc cổng đó; thao tác file thủ công chưa đạt DoD P2.
