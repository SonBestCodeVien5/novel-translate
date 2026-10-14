# Kế hoạch triển khai app dịch novel

Trạng thái: tài liệu thiết kế; chưa triển khai hoặc benchmark.
Lộ trình và cổng quyết định: [ROADMAP.md](ROADMAP.md).
Bước tiếp theo là P0; các phase chưa có người nhận việc cụ thể.

## 1. Mục tiêu và phạm vi

- App một người dùng: nhập sách, dịch theo chương, sửa bản dịch, xuất sách.
- Máy Dell Vostro giữ dữ liệu và giao diện; Colab cung cấp GPU theo phiên tương tác.
- EN → VI là giả định làm việc, cần xác nhận ở P0; chưa khóa model hay ngân sách.
- MVP hỗ trợ TXT trước, EPUB sau; crawler một website nằm ở P4, không bị bỏ khỏi mục tiêu.
- Giữ nguyên bản gốc, thứ tự chương, bản dịch máy và lịch sử sửa tay.
- Không có React, Celery, Redis, RAG, Docker, nhiều người dùng hay dịch vụ Colab luôn bật trong MVP.
- Không cam kết tốc độ/chất lượng trước khi đo trên sách và phần cứng thực tế.

## 2. Quyết định còn mở

| Quyết định | Thông tin cần có | Checkpoint |
| --- | --- | --- |
| Ngôn ngữ và tiêu chí văn phong | Xác nhận EN → VI, mẫu bản dịch mong muốn | P0 |
| Model và cách chạy | Hai ứng viên, quyền truy cập, giấy phép, VRAM | P0 |
| Ngân sách | Hạn mức API/GPU và số chương dự kiến | P0 |
| Máy local | Đã xác nhận WSL; cần RAM, dung lượng, distro và Python khả dụng | P0/P1 |
| Website crawl đầu tiên | URL, quyền truy cập, cấu trúc chương | Trước P4 |
| Chất lượng chấp nhận được | Ngưỡng sửa tay và lỗi trọng yếu | Chốt trước khi chấm P0 |

Thiếu các thông tin này không cản viết tài liệu hoặc làm fake provider ở P1.
Không chọn model sản xuất hoặc hứa thời gian hoàn tất khi chưa qua P0.

## 3. Kiến trúc nhỏ nhất

```text
Trình duyệt → FastAPI + Jinja2 → SQLite và thư mục sách local
                                  ↓ xuất batch
                         Drive: manifest + source bất biến
                                  ↓ runner CLI (sau kiểm chứng) / notebook
                         Phiên Colab → model
                                  ↓ ghi từng kết quả hoàn tất
                         Drive: result bất biến
                                  ↓ nhập có kiểm tra
                         FastAPI → review → TXT/EPUB
```

- FastAPI phục vụ trang server-rendered, upload, review, export và nhập kết quả.
- Backend local là chủ sở hữu duy nhất của SQLite; runner Colab không mở DB.
- SQLite đặt trên ổ local; Drive chỉ trao đổi file, không chứa DB dùng chung.
- Batch là ảnh chụp đầu vào; sửa glossary/prompt tạo batch mới, không sửa batch cũ.
- P2 kiểm chứng Colab CLI trên WSL trước khi làm script local điều phối theo yêu cầu; notebook là fallback.
- Script tạo phiên, truyền batch, chạy runner, nhận/validate/import result qua backend local rồi giải phóng phiên; dùng chung batch, validator và checkpoint với notebook.
- Kết quả mỗi chunk phải được lưu bền vững ngoài VM (Drive hoặc local) trước khi coi là checkpoint; không chờ cuối job mới tải.
- Auth/permission cần người dùng khi CLI hoặc Drive yêu cầu; không đưa credential/token vào bundle hay log.
- CLI là phương án tạm, chưa kiểm chứng trên WSL/tài khoản thực; nếu không đạt P2-03, ghi lý do hoãn và dùng notebook do người dùng mở/chạy. Colab không là dịch vụ luôn bật.
- Khi runtime mất: load model lại, bỏ qua result đã xác thực và lưu bền vững; dịch lại chunk dở.
- Local ghi DB trong transaction ngắn; không giữ transaction khi chạy model hoặc chờ Drive.
- Tác vụ local dài có trạng thái lưu DB và được tiếp tục qua thao tác rõ ràng trong UI.
- P1 ưu tiên chạy tuần tự; không cần hàng đợi phân tán hoặc worker lease.

## 4. Cấu trúc mã nguồn đề xuất

```text
app/
  main.py                  # routes và cấu hình local
  db.py                    # schema, transaction, truy vấn
  importers.py             # TXT trước, EPUB sau
  translation.py           # chunk, prompt, provider, thứ tự chạy
  bundles.py               # manifest/result, kiểm tra và nhập
  exporters.py             # TXT/EPUB
  templates/               # danh sách sách, chương, review, jobs
  static/                  # CSS tối thiểu
notebooks/translate.ipynb   # batch runner Colab tương tác
tests/                     # fixture nhỏ và kiểm thử luồng lỗi
data/                      # DB, nguồn, batch; bỏ khỏi version control
docs/                      # thiết kế, hướng dẫn vận hành, kết quả P0
```

Chỉ tách module khi có mã tương ứng; không sinh sẵn framework provider/plugin.
Provider đầu tiên có cùng hợp đồng đầu vào/đầu ra với fake provider P1.

## 5. Dữ liệu tối thiểu và quyền sở hữu

| Thực thể | Trường và ràng buộc chính |
| --- | --- |
| Book | id, tên, ngôn ngữ, định dạng, raw SHA-256, đường dẫn nguồn, import version |
| Chapter | id, book_id, ordinal duy nhất trong sách, tiêu đề, source locator, source hash |
| Chunk | id, chapter_id, ordinal, source text/hash, offsets/block IDs, chunker version |
| Job | id, book_id, manifest hash, snapshot cấu hình, trạng thái, thời điểm, lỗi tổng hợp |
| Result | id, job_id + chunk_id duy nhất, provenance, bản dịch máy, checksum, lỗi/attempts |
| Glossary | book_id, canonical term, aliases, bản dịch, ghi chú xưng hô, revision |
| Revision | chapter/chunk target, nội dung sửa tay, base result hash, revision tăng dần |

- Có thể lưu snapshot glossary/cấu hình và lỗi bằng JSON trong Job/Result; chưa thêm bảng nếu không cần truy vấn.
- Source gốc bất biến; text đã chuẩn hóa lưu riêng, không thay thế file gốc.
- Mỗi chunk biết vị trí nguồn để xuất lại đúng thứ tự, không ghép theo thời điểm result đến.
- Bản dịch máy và bản sửa tay độc lập; bản sửa hiện hành được ưu tiên khi xuất.
- Revision lưu base revision/result để phát hiện hai lần sửa dựa trên cùng bản cũ.
- Backup DB đang chạy bằng SQLite backup API hoặc consistent snapshot; không copy riêng main DB khi có WAL.
- Backup/restore giữ DB và assets nguồn/batch nhất quán; khôi phục thử trước khi coi backup là đủ.

## 6. State machine và thứ tự dịch

- Job: `draft → exported → running → partial → completed`; có `failed` hoặc `cancelled`.
- `running` là trạng thái quan sát được từ runner/results, không chứng minh runtime còn sống.
- Chunk/result: `pending → in_progress → completed`; lỗi thành `retryable_failed`, `failed` hoặc `needs_review`.
- Resume đưa chunk `in_progress` không có result hợp lệ về `pending`; không nhận output chưa hoàn tất.
- Job chỉ `completed` khi mọi chunk dự kiến có kết quả hợp lệ cho đúng snapshot.
- Hủy job không xóa source, kết quả hay revision; kết quả đến muộn vẫn phải qua kiểm tra import.
- Chạy theo chapter ordinal rồi chunk ordinal; chunk không cắt giữa câu nếu tránh được.
- Đếm token bằng tokenizer đúng model, gồm template, glossary, context và output reserve.
- Ghi input/output token bằng `null` nếu provider không cung cấp và chưa đo được; không ước lượng thành số thực đo.
- Chunk quá dài phải chia lại trước khi gửi; không cắt âm thầm khi model trả thiếu.
- Output dừng do max tokens hoặc nghi thiếu đoạn phải `failed`/`needs_review`, chưa tính hoàn tất cho job hoặc export chính thức.
- Checker kỹ thuật không bảo đảm đủ ý về ngữ nghĩa; P0 và review của người đọc vẫn phải kiểm tra nội dung.
- MVP dùng glossary và context nguồn trước đó có giới hạn, không phụ thuộc bản dịch chunk trước.
- Ghi rõ context policy và hash vào snapshot để kết quả có thể truy vết.
- Nếu sau này dùng bản dịch trước làm context, ghi dependency result hash; đổi upstream làm downstream stale.
- Chương mới không tự kế thừa đại từ từ suy đoán không được người dùng duyệt.

## 7. Hợp đồng batch và kiểm tra tính toàn vẹn

Bundle JSON gồm manifest và một file result cho mỗi chunk hoàn tất; dùng UTF-8.
Schema có `schema_version`; validator từ chối version/field lạ, kiểu sai, ID trùng và kích thước vượt giới hạn.

| File | Trường bắt buộc dự kiến |
| --- | --- |
| Manifest | schema_version, job_id, book_id, created_at, source/target language, source hash |
| Snapshot | model ID + revision, tokenizer ID + revision, generation parameters, prompt/version/hash, prompt/template text hoặc pinned artifact kèm trong bundle |
| Snapshot tiếp | glossary revision/hash và toàn bộ entries/aliases/ghi chú xưng hô, chunker version/config/hash, context policy/hash |
| Chunk entry | chunk_id, chapter_id, ordinals, source locator/text/hash, context text/hash hoặc source entry IDs có thứ tự + quy tắc dựng deterministic, expected input hash |
| Result | schema_version, job_id, manifest hash, chunk_id, expected input hash, status=completed |
| Provenance | model/tokenizer revisions thực chạy, prompt/glossary/chunker hashes, parameters, runner version |
| Payload | translated_text, input/output token counts nếu có, started_at, completed_at, payload SHA-256 |

- Quy định một cách canonical hóa JSON cho hash; không hash phụ thuộc thứ tự key tùy ý.
- Bundle tự chứa đủ prompt, glossary và context để runner CLI/notebook thực thi; hash/revision chỉ để kiểm chứng, không thay dữ liệu đầu vào.
- Chốt trước P1: JSON key tăng dần, separator gọn, UTF-8 không BOM, không NaN; hash SHA-256 lowercase hex.
- ID là chuỗi UUID, ordinal là số nguyên từ 0, timestamp UTC RFC3339; text giữ nguyên Unicode, không tự normalize lúc hash.
- Result checksum tính trên object bỏ trường checksum; manifest hash tính trên toàn manifest canonical, không tự chứa hash của chính nó.
- Hash raw file khác hash text chuẩn hóa; cả hai được giữ để phân biệt nguồn và pipeline.
- Dùng revision cố định khi nhà cung cấp hỗ trợ; ghi rõ nếu API chỉ cung cấp tên model không bất biến.
- Hash là kiểm tra toàn vẹn, không chứng minh file đáng tin hoặc model đã chạy đúng.
- Runner CLI/notebook ghi file tạm, đóng file rồi công bố result hoàn tất; không coi thao tác sync Drive là atomic.
- Import chỉ nhận file đủ bytes, parse được, checksum đúng; file đang chuyển được bỏ qua và báo chờ.
- Import từng result trong transaction và lưu checkpoint theo job/chunk/hash; crash không nhận nửa result.
- Import lại cùng result là no-op; cùng job/chunk nhưng payload khác đưa vào conflict, không ghi đè.
- Manifest/input/provenance lệch snapshot: giữ file để chẩn đoán, đánh dấu stale/rejected và yêu cầu batch đúng.
- Glossary/prompt/source thay đổi tạo job mới; UI chỉ rõ kết quả cũ thuộc snapshot nào.
- Result đến sau sửa tay không thay revision; UI cho so sánh rồi áp dụng có chủ đích.
- Không dùng thời gian sửa file làm bằng chứng kết quả mới hơn hoặc đúng hơn.

## 8. Nhập, review và xuất

- Import cùng raw hash + import version + tùy chọn chuẩn hóa là no-op, trả sách đã có.
- Cùng tên nhưng khác hash là nguồn mới cần xem xét; không thay sách cũ tự động.
- TXT: nhận encoding có kiểm tra; cho xem và sửa cách tách heading/chương trước khi chốt.
- TXT không có heading rõ: cho phép một chương hoặc đánh dấu thủ công, không đoán chắc chắn.
- Glossary quản lý canonical term, aliases, kiểu chữ và ghi chú ngữ cảnh.
- Xưng hô lưu theo cặp nhân vật/ngữ cảnh khi cần; không thay thế chuỗi toàn cục mù quáng.
- Thay glossary chỉ ảnh hưởng job mới; UI liệt kê chunk có thể cần dịch lại, giữ sửa tay.
- Review hiển thị nguồn và đích, trạng thái thiếu/stale, lưu revision có kiểm tra base revision.
- TXT export theo ordinal, giữ heading đã duyệt; báo rõ chunk thiếu và yêu cầu chọn xuất nháp.
- EPUB nhập theo spine của package, giữ mapping block/XHTML/resource, không dựa tên file.
- EPUB xuất thay text node/block đúng mapping; giữ thứ tự spine, metadata, ảnh, link và tài nguyên.
- Escape nội dung dịch vào XHTML; kiểm tra XML/XHTML, manifest/spine và liên kết nội bộ trước xuất.
- Chưa xử lý được một cấu trúc EPUB thì báo lỗi hoặc yêu cầu review, không xuất file có vẻ thành công.

## 9. Lỗi, giới hạn và ranh giới tin cậy

- Retry chỉ lỗi tạm thời như timeout/rate limit/network; đề xuất tối đa 3 lần với backoff và jitter.
- Không tự cấp lại GPU vô hạn hoặc vượt trần thử/ngân sách; MVP ưu tiên người dùng bấm resume sau mất phiên.
- Không retry tự động lỗi quyền truy cập, schema, checksum, model không tương thích hoặc input vượt context.
- Lỗi OOM dừng để giảm batch/chunk hoặc đổi model; thay cấu hình phải tạo snapshot mới.
- Timeout không chứng minh provider chưa xử lý; dùng request ID/idempotency khi provider hỗ trợ.
- Giới hạn kích thước upload, archive, số entry và tỷ lệ giải nén; chống zip bomb/path traversal/symlink.
- Nguồn sách là dữ liệu không tin cậy: không làm theo lệnh trong truyện, không cấp tool cho model.
- Template tách instruction khỏi source; vẫn review vì prompt không bảo đảm chống injection tuyệt đối.
- Jinja2 escape mặc định; không render HTML nguồn/model bằng `safe`; preview EPUB phải được làm sạch.
- Backend bind loopback mặc định; upload/export path do server tạo, không nhận đường dẫn tùy ý.
- API key ở secret của phiên hoặc biến môi trường; không ghi vào notebook output, DB snapshot hay Drive.
- Bundle từ Drive vẫn phải qua validator; thông báo lỗi không lộ secret hoặc toàn bộ nội dung sách.
- Chỉ P4 có fetch URL: chặn SSRF tới loopback/private/link-local, kiểm tra lại mỗi redirect và DNS đích.
- Crawler có timeout, giới hạn response, allowlist site, rate limit; không vượt đăng nhập/paywall.

## 10. Kiểm thử và điều kiện hoàn thành

- P0 chấm 5 chương có đối thoại, tên riêng, xưng hô, văn miêu tả và chương dài.
- Đo token vào/ra, tốc độ, chi phí và thời gian sửa; lưu model/config và phép đo thật.

Mẫu benchmark: một dòng mỗi chương/ứng viên, thêm 10 dòng trước khi chạy; ô chưa đo để trống.

| Chương / ứng viên | Model revision / cấu hình | Token vào / ra | Load / dịch (s) | Sửa tay (phút) | Baseline (phút) | Chi phí / GPU time | Lỗi và đạt ngưỡng? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 / A | | | | | | | |
| 1 / B | | | | | | | |

- P1 kiểm thử fake provider từ TXT tới export sau restart; duplicate import không nhân dữ liệu.
- Fault tests: crash giữa import, file thiếu bytes/checksum sai, result tới chậm/trùng/xung đột.
- Thử sửa glossary và sửa tay trong khi job cũ đang chạy; không mất sửa tay, stale được nhận diện.
- P2-03 kiểm chứng CLI trên WSL/tài khoản thực: auth, GPU/quota, truyền file, checkpoint ngoài VM và ngắt/resume.
- P2-04 chỉ làm script điều phối sau khi CLI đạt; thử ngắt runner CLI/notebook, load lại model và resume chỉ từ result lưu bền vững.
- P3 nối script đã kiểm chứng vào nút Dịch, tiến độ và resume; nhận đủ result thì chuyển sang review, duyệt/export chính thức vẫn do người dùng chủ động.
- EPUB fixture có spine khác tên file, ảnh, link, ký tự đặc biệt; xuất phải giữ cấu trúc hợp lệ.
- P3 thử lưu đồng thời hai tab và hiển thị lỗi bằng bàn phím/screen reader cơ bản.
- P4 thử redirect tới mạng nội bộ, URL ngoài site và giới hạn tải; không chỉ kiểm thử trang đẹp.
- Mỗi phase phải qua tiêu chí trong [ROADMAP.md](ROADMAP.md) trước khi mở rộng.

## 11. Cơ sở tham khảo và giới hạn bằng chứng

- [Colab CLI](https://github.com/googlecolab/google-colab-cli): phương án điều phối tạm cho P2-03/P2-04, chưa chạy hoặc xác minh trên WSL/tài khoản thực.
- [Colab FAQ](https://research.google.com/colaboratory/faq.html): giới hạn runtime/tài nguyên không phải cam kết always-on.
- [SQLite qua mạng](https://sqlite.org/useovernet.html): cơ sở để DB ở local, không mở chung qua Drive.
- [Colab VS Code](https://github.com/googlecolab/colab-vscode): tùy chọn tương tác, không biến Colab thành worker bền vững.
- [TranslateGemma 12B](https://huggingface.co/google/translategemma-12b-it): ứng viên cần thử; đọc template riêng và giới hạn input 2K, không giả định long context.
- [book-translator](https://github.com/KazKozDev/book-translator) và [TranslateBooksWithLLMs](https://github.com/hydropix/TranslateBooksWithLLMs): tham khảo README, chưa chạy hoặc xác minh chất lượng.
