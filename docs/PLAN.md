# Kế hoạch app đọc và dịch novel

Trạng thái: P1 provider giả đã triển khai/kiểm thử; user xác nhận đã chấm và
chọn `Qwen/Qwen3.5-4B` làm provider tích hợp ngày 15/10/2026. Báo cáo/số đo
chấm chưa được lưu trong repo; không tự suy ra 25%, 18/18, đủ hai model hay
zero critical errors. `criteria.json` còn stale (`not_run`/`decision=null`) và
chưa được cập nhật theo xác nhận user; chưa kết luận formal P0 quality phase.
P2 Qwen3.5 v2 có offline app flow/UI review, notebook fallback và CLI/UI điều
phối trên alias T4 đã đăng ký. Live smoke trên fixture 2 chương/2 chunk đạt với
GPU/model inference và Drive checkpoint; resume sau restart kernel cùng VM đã
giữ checkpoint byte-identical, duplicate no-op và bản sửa tay. Chưa kiểm mất
VM/new VM, full 390 chương, native EPUB reader hoặc chất lượng/tốc độ.
EPUB import/export có profile giới hạn; glossary và backup/restore đã có. Xem
[INTEGRATION](INTEGRATION.md) và [REAL_BATCH](REAL_BATCH.md).
Lộ trình và cổng quyết định: [ROADMAP.md](ROADMAP.md).
Bằng chứng và readiness P2/P3 nằm trong [INTEGRATION.md](INTEGRATION.md);
không dùng integration/offline code thay quality evidence P0. Bằng chứng P1 nằm
trong [P1.md](P1.md).

## 1. Mục tiêu và phạm vi

- App đọc truyện local nhẹ là luồng chính: người dùng mở và đọc raw, bản dịch,
  hoặc song ngữ; không cần tạo job dịch để đọc raw. Dịch theo chương/manifest,
  sửa bản dịch và review vẫn là công cụ hỗ trợ cải thiện dần, không phải điều
  kiện để đọc.
- Máy Dell Vostro giữ dữ liệu và giao diện; Colab cung cấp GPU theo phiên tương tác.
- EN → VI, ngân sách 0 đồng; Colab miễn phí dùng một hoặc nhiều phiên theo
  quota/runtime thực tế. User chọn `Qwen/Qwen3.5-4B` làm provider tích hợp ngày
  15/10/2026. Mốc tối đa 2 lần thử/model và tổng 4 phiên thuộc kế hoạch
  benchmark P0 lịch sử, không phải trần mọi phiên dịch sách.
- MVP hỗ trợ TXT trước, EPUB sau. Crawler P4 đang hoãn vì user đã có dữ liệu;
  crawler không phải điều kiện để hoàn thành reader local.
- Giữ nguyên bản gốc, thứ tự chương, bản dịch máy và lịch sử sửa tay.
- Không có React, Celery, Redis, RAG, Docker, nhiều người dùng hay dịch vụ Colab luôn bật trong MVP.
- Không cam kết tốc độ/chất lượng trước khi đo trên sách và phần cứng thực tế.

### Hợp đồng reader local (R1) và vị trí đọc (R2)

- Đọc raw không tạo job và không cần network, tokenizer, GPU hay runtime dịch.
- Người dùng chọn rõ job dịch cần đọc; không tự chọn job mới nhất, ghép chunk
  P1/v1 với v2, hoặc trộn kết quả từ các job khác nhau.
- Trong job đã chọn, đọc revision hiện hành trước bản máy khi có revision; giữ
  sửa tay và cảnh báo rõ cho đoạn chưa có result, chưa review hoặc stale. Job
  partial vẫn đọc được và đoạn còn thiếu phải được báo rõ.
- Đọc không thay đổi trạng thái approved. Từ đoạn đọc có thể mở review đúng
  chunk/job để sửa hoặc duyệt.
- Resume translation tiếp tục cùng manifest bất biến. Việc nhớ vị trí đọc độc
  lập với review và checkpoint dịch: SQLite local lưu một vị trí gần nhất mỗi
  sách gồm chapter ID, lựa chọn raw/job/mode và anchor thuộc đúng job nếu có;
  không cam kết đồng bộ vị trí pixel.
- R1 có reader `/books/{book_id}/read`, chọn `chapter`, `mode` và `job_id` v2
  tường minh; P1 FAKE giữ luồng review riêng. Raw lấy nguồn chương đã nhập;
  dịch/song ngữ dùng chunk của job v2. R2 lưu vị trí vẫn chưa triển khai. Xem
  [đánh giá hướng đi](DIRECTION_REVIEW.md) cho bối cảnh trước R1.

### Cải thiện bản dịch theo bằng chứng (chưa tự học)

- Sửa revision trong review cải thiện bản local; giữ result máy và lịch sử sửa.
- Glossary được snapshot vào job mới, không mutate job cũ.
- Gom mẫu lỗi có nguồn/job/chunk và đối chiếu bản sửa trước khi điều chỉnh
  prompt hoặc bounded context; chỉ mở rộng context khi lỗi cụ thể chứng minh cần.
- Không có tự học/fine-tune hay tự sửa chương cũ. Selective retranslate chưa
  triển khai; job/manifest cũ vẫn bất biến.

## 2. Quyết định còn mở

| Quyết định | Thông tin cần có | Checkpoint |
| --- | --- | --- |
| Tiêu chí văn phong | Đã chốt: tiếng Việt tự nhiên, giữ giọng nhân vật và tên riêng | P0 |
| Model và cách chạy | User chọn Qwen/Qwen3.5-4B; pinned profile/runtime smoke đã đạt trên fixture nhỏ; full-book, VM-loss durability và quality benchmark còn mở | P2/P0 |
| Ngân sách | Đã chốt 0 đồng; 4 phiên/2 lần thử mỗi model chỉ là budget benchmark P0 lịch sử, không giới hạn lượt dịch sách | P0 |
| Máy local | Đã xác nhận WSL; cần RAM, dung lượng, distro và Python khả dụng | P0/P1 |
| Website crawl đầu tiên | URL, quyền truy cập, cấu trúc chương | Trước P4 |
| Chất lượng chấp nhận được | Đã chốt: không bỏ đoạn, mọi chunk hoàn tất, 0 lỗi sai ý trọng yếu sau review, saving tổng ≥25% | P0 |

Thiếu các thông tin runtime/profile v2 không cản chuẩn bị tích hợp. Model tích hợp
đã được user chọn; formal P0 benchmark metrics/go-no-go vẫn chưa có trong repo.

## 3. Kiến trúc nhỏ nhất

```text
Trình duyệt → FastAPI + Jinja2 → SQLite và thư mục sách local
                                  ↓ xuất batch
                         Drive: manifest + source bất biến
                                  ↓ runner CLI trên alias đã đăng ký / notebook fallback
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
- App có notebook Qwen3.5 v2 làm fallback file workflow và CLI/UI v2 dùng alias T4 đã đăng ký. Live smoke trên fixture 2 chương/2 chunk đạt: output 36/34 token EOS; `--limit 1`, restart kernel cùng VM rồi resume chunk hai; checkpoint Drive đầu đọc lại byte-identical, duplicate no-op và edits được giữ. Nút UI trên job hoàn tất thu hai duplicate.
- CLI/UI không tự tạo hay giải phóng VM; cần Drive mount, pinned dependencies và kernel alias idle. Notebook vẫn cho phép thao tác file thủ công; cả hai dùng chung runner/manifest/result contract.
- Kết quả mỗi chunk phải được lưu bền vững ngoài VM (Drive hoặc local) trước khi coi là checkpoint; không chờ cuối job mới tải.
- Auth/permission cần người dùng khi CLI hoặc Drive yêu cầu; không đưa credential/token vào bundle hay log.
- Live evidence chỉ là smoke fixture nhỏ và restart kernel trên cùng VM; không chứng minh mất VM/new VM, full-book run, quota dài hạn hoặc chất lượng dịch. Colab không là dịch vụ luôn bật.
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

Schema SQLite có 6 bảng v1, 4 bảng real v2 và glossary theo sách; trạng thái schema
đích và giới hạn migration nằm ở
[SQLITE_SCHEMA.md](SQLITE_SCHEMA.md); bảng dưới đây là hợp đồng mục tiêu,
không phải danh sách cột hiện có.

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
- Backup ZIP v1 chụp SQLite bằng backup API dưới writer lock, kèm các thư mục
  app sở hữu (`sources`, `batches`, `results`, `rejected`, `real-batches`,
  `real-results`) và inventory size/SHA-256. Không kèm auth, Colab CLI state,
  log hoặc file ngoài các thư mục này. Restore kiểm inventory, schema, foreign
  keys và tham chiếu nguồn/batch/result; chỉ công bố vào thư mục mới chưa tồn
  tại, không ghi đè thư viện đang mở. Bản đầu hỗ trợ atomic publish trên Linux/WSL.

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
- Khi nối provider thật, tạo job plan bất biến theo tokenizer/budget; không âm thầm chia lại chunks/job cũ hoặc mất revision. Migration cần test bảo toàn nguồn/sửa tay.
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
- P2 offline bundle app/Colab v2 hỗ trợ Qwen3.5 và các snapshot Qwen v2 cũ; `chat_template_kwargs.enable_thinking=false` được snapshot/hash và dùng cùng planner/runner. P0 plan/results/sessions vẫn khác schema, không import sang v2. SQLite khai báo 6 bảng v1 + 4 bảng `real_*`; xem [schema](SQLITE_SCHEMA.md). Readiness ở [INTEGRATION](INTEGRATION.md).
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
- Glossary theo sách có revision tăng dần và tối đa 100 mục. Mỗi mục gồm `term`,
  `translation` (tối đa 200 ký tự), `aliases` (tối đa 10 tên, mỗi tên 200 ký tự)
  và `notes` (tối đa 1.000 ký tự). Term/alias không trùng nhau khi bỏ qua hoa
  thường. Lưu kiểm base revision để tránh hai tab ghi đè nhau; revision 0 chỉ
  dành cho glossary rỗng ban đầu. Job mới đóng băng toàn bộ entries/revision/hash;
  planner và runner cùng dùng entries trong prompt và tính vào token budget.
  Đổi glossary không hủy duyệt hay cấm xuất job cũ; UI báo khác revision để
  người dùng chủ động tạo job mới. Snapshot rỗng cũ giữ nguyên bytes/hash/input.
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
- Review v2 hiển thị một chương mỗi lần, lọc thiếu result/chưa duyệt/đã duyệt;
  tổng tiến độ vẫn tính toàn job. Đổi trang/lọc hoặc lưu không thay selection job.
- Trang sách P1 mặc định mở chương đầu; chọn theo tên/số thứ tự hoặc trước/tiếp.
  P1 và review v2 chỉ hydrate chunk/result/revision chương chọn; caller không
  truyền chương vẫn nhận đầy đủ cho CLI/export. Các trang phụ dùng metadata
  sách; manifest/source v2 vẫn được validate toàn bộ, không có cache.
- Nhập nhiều result v2 theo job bằng nhiều JSON hoặc một ZIP: kiểm container và
  giới hạn trước, sau đó nhập độc lập từng chunk qua validator hiện có. Báo riêng
  imported/duplicate/rejected; một payload lỗi không làm mất chunk hợp lệ khác.
  ZIP chỉ đọc trong bộ nhớ, không extract; không nhận file thuộc job khác.
- TXT export theo ordinal, giữ heading đã duyệt; báo rõ chunk thiếu và yêu cầu chọn xuất nháp.
- EPUB nhập theo spine của package, giữ mapping block/XHTML/resource, không dựa tên file.
- EPUB xuất thay text node/block đúng mapping; giữ thứ tự spine, metadata, ảnh, link và tài nguyên.
- Profile EPUB đầu tiên chỉ tự thay paragraph khi số đoạn nguồn/đích khớp và
  mỗi đoạn nguồn có một text slot rõ ràng theo mapping; hỗ trợ anchor/ảnh mà
  không đoán alignment trong đoạn có nhiều text node. Mismatch hoặc mixed inline
  không ánh xạ chắc chắn thì từ chối, yêu cầu review/TXT. TXT source có thể xuất
  EPUB mới theo thứ tự chương. Official EPUB dùng cùng guard duyệt hiện hành
  như official TXT; raw EPUB luôn bất biến.
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
- P2-03 đã smoke batch v2 trên T4: auth/GPU, truyền file, EOS, Drive checkpoint readback và resume sau restart kernel cùng VM trên fixture 2 chunk. Mất VM/new VM, full book, timeout live và benchmark còn mở.
- P2-04 CLI/UI chạy trên alias/kernel đã đăng ký; không tạo hoặc giải phóng VM. Import per-chunk, timeout/partial behavior và resume dùng chung contract với notebook.
- P3 UI có nút chạy/resume; result chuyển sang review, duyệt/export chính thức vẫn do người dùng chủ động.
- EPUB fixture có spine khác tên file, ảnh, link, ký tự đặc biệt; xuất phải giữ cấu trúc hợp lệ.
- P3 thử lưu đồng thời hai tab và hiển thị lỗi bằng bàn phím/screen reader cơ bản.
- P4 thử redirect tới mạng nội bộ, URL ngoài site và giới hạn tải; không chỉ kiểm thử trang đẹp.
- Mỗi phase phải qua tiêu chí trong [ROADMAP.md](ROADMAP.md) trước khi mở rộng.
- Chất lượng/25% tiết kiệm là tiêu chí benchmark P0 đã chốt nhưng chưa có report
  trong repo; không tuyên bố đạt. Quality gate lịch sử này không chặn việc xây
  reader local raw/dịch/song ngữ R1/R2. Reader acceptance xem
  [ROADMAP.md](ROADMAP.md); hợp đồng reader tương lai ở mục 1 và đánh giá hiện
  trạng tại [DIRECTION_REVIEW.md](DIRECTION_REVIEW.md).

## 11. Cơ sở tham khảo và giới hạn bằng chứng

- [Colab CLI](https://github.com/googlecolab/google-colab-cli): live smoke batch v2 đạt trên fixture 2 chunk với T4, gồm checkpoint Drive và resume sau restart kernel cùng VM; chưa kiểm mất VM/new VM hoặc full book.
- [Colab FAQ](https://research.google.com/colaboratory/faq.html): giới hạn runtime/tài nguyên không phải cam kết always-on.
- [SQLite qua mạng](https://sqlite.org/useovernet.html): cơ sở để DB ở local, không mở chung qua Drive.
- [Colab VS Code](https://github.com/googlecolab/colab-vscode): tùy chọn tương tác, không biến Colab thành worker bền vững.
- [TranslateGemma 12B](https://huggingface.co/google/translategemma-12b-it): ứng viên cần thử; đọc template riêng và giới hạn input 2K, không giả định long context.
- [book-translator](https://github.com/KazKozDev/book-translator) và [TranslateBooksWithLLMs](https://github.com/hydropix/TranslateBooksWithLLMs): tham khảo README, chưa chạy hoặc xác minh chất lượng.
