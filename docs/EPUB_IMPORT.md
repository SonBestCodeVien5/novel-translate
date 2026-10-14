# Nhập EPUB local và luồng Colab

Phạm vi được người dùng mở ngày 14/10/2026: nhập EPUB vào SQLite local bằng CLI.
Không thay notebook đang chạy; chưa mở provider sản xuất, EPUB export hay điều phối
Colab tự động. Chưa có kết quả go/no-go P0.

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

## Luồng đã chốt

```text
EPUB local → backend parse spine → SQLite local + raw EPUB/mapping
                                  ↓ xuất job snapshot JSON
                         Drive: batch/manifest + source chunks
                                  ↓ CLI đã kiểm chứng hoặc notebook
                         Colab: load model → dịch từng chunk
                                  ↓ lưu mỗi chunk hoàn tất
                         Drive: result + timing/provenance/checksum
                                  ↓ tải về và validate
                         backend local → nhập SQLite → review → xuất
```

SQLite chỉ do backend local truy cập. Không upload database lên Drive hoặc mở nó
trong Colab. Batch gồm ID/thứ tự, source text/hash, prompt/glossary/config và model
revision; kết quả phải khớp đúng batch trước khi nhập. Import trùng là no-op;
kết quả xung đột hoặc lệch snapshot bị từ chối, không ghi đè bản sửa tay.

Drive dùng để giữ checkpoint ngoài VM. Không chờ dịch toàn sách xong mới tải
result về; có thể nhận từng phần đã hoàn tất. Mất phiên thì load lại model,
validate checkpoint, bỏ qua phần đã lưu và dịch lại chunk dở.

## Giới hạn kết nối hiện tại

Notebook P0 hiện là runner benchmark riêng; corpus/results của nó chưa cùng schema
bundle app P1 và chưa được import tự động vào SQLite. Cần nối provider, tokenizer
chunking và hợp đồng batch/result ở P2 trước khi dùng luồng end-to-end thật.

[Colab CLI chính thức](https://github.com/googlecolab/google-colab-cli) hỗ trợ
provision runtime, mount Drive, execute, upload/download và stop. Máy hiện tại
chưa có CLI; chưa kiểm chứng auth/GPU/quota/transfers/resume trên WSL/tài khoản
người dùng (P2-03). Chỉ làm script điều phối sau kiểm chứng; notebook là fallback.
