# Tổng quan dự án Novel Translate

## Trạng thái và cách đọc

Repo có luồng P1 giả riêng và batch/review v2 cho Qwen3.5: tạo manifest, chạy
notebook/CLI, nhập một/nhiều result, sửa/duyệt theo chương, xuất TXT/EPUB,
glossary theo sách và backup/restore. Live smoke T4 đã chạy fixture 2 chương/2
chunk và resume sau restart kernel cùng VM; chưa kiểm mất VM/new VM, full 390
chương, benchmark tốc độ/chất lượng hay native EPUB reader. Hướng sản phẩm được
chốt là app đọc local nhẹ: raw/dịch/song ngữ là luồng chính, review tiếp tục để
cải thiện dần. Reader local R1 có raw/dịch/song ngữ, chọn job v2 tường minh
và nối review; reading progress R2 chưa triển khai. Xem [đánh giá hướng đi](DIRECTION_REVIEW.md).
Trạng thái vận hành mới nhất nằm ở [HANDOFF.md](HANDOFF.md). [P1.md](P1.md) ghi bằng chứng/giới hạn
cụ thể. Nội dung bên dưới mô tả hướng thiết kế, không cam kết chất lượng.

- Tài liệu này: bối cảnh, mục tiêu và các lựa chọn tổng thể.
- [PLAN.md](PLAN.md): nguồn chính cho kiến trúc, hợp đồng dữ liệu và bất biến.
- [ROADMAP.md](ROADMAP.md): nguồn chính cho backlog P0–P4, phụ thuộc và tiêu chí hoàn thành.
- [WORKFLOW.md](WORKFLOW.md) và [AGENTS.md](../AGENTS.md): cách làm việc và quy tắc agent.

Khi cần đổi thiết kế hoặc phạm vi, cập nhật PLAN/ROADMAP tương ứng rồi đồng bộ
phần tổng quan liên quan. Tài liệu này không thay thế hợp đồng kỹ thuật hoặc
chỉ thị làm việc, và không cần nạp toàn bộ vào mọi nhiệm vụ.

## Mục tiêu sản phẩm

Xây dựng app đọc truyện cá nhân local nhẹ, hỗ trợ đọc raw, bản dịch và song ngữ;
dịch bằng LLM, glossary, review/sửa bản dịch và export là các công cụ để cải
thiện nội dung dần. Người dùng đã xác nhận EN → VI, ngân sách 0 đồng, Colab miễn
phí theo phiên, văn phong tiếng Việt tự nhiên giữ giọng nhân vật/tên riêng.
Mốc tối đa 2 lần thử/model và tổng 4 phiên ngày 14/10/2026 thuộc benchmark P0
lịch sử, không giới hạn các phiên dịch sách.

Giá trị mong muốn là giảm thời gian dịch và sửa mà vẫn giữ nghĩa, tên riêng,
thuật ngữ, tính cách và xưng hô nhất quán. Giữ bản gốc và sửa tay là yêu cầu
bắt buộc; bản dịch máy luôn cần kiểm tra, nhất là thiếu đoạn hoặc sai ý.

Phạm vi là một người dùng: TXT trước, EPUB sau. Raw phải đọc được không cần job;
bản dịch chọn theo job rõ ràng và partial result vẫn đọc được. Không yêu cầu
duyệt hết mới đọc. Review/glossary tiếp tục có vai trò cải thiện bản dịch; app
đã có reader riêng và review UI; reading progress chưa triển khai. User đã
có dữ liệu và hoãn crawling; xem ROADMAP cho thứ tự tiếp theo.

## Kiến trúc đã chọn cho bản đầu

```text
Trình duyệt → FastAPI + Jinja2 → SQLite và dữ liệu sách local
                                  ↓ xuất batch bất biến
                         Drive: manifest + source + snapshots
                                  ↓ runner CLI trên alias có sẵn / notebook fallback
                         Colab → model → result từng chunk
                                  ↓ nhập và kiểm tra ở local
                         Review → TXT/EPUB
```

Máy Dell Vostro giữ giao diện, nguồn sách, database và trạng thái ứng dụng.
Đã xác nhận dùng WSL; RAM, distro, Python và dung lượng chưa xác nhận. Không
suy ra khả năng chạy model hay trần dung lượng từ tên thiết bị. Backend local là nơi duy nhất truy cập SQLite.

Colab xử lý batch bằng file, không phải backend luôn bật. CLI/UI v2 điều phối
trên alias/kernel T4 đã đăng ký, kiểm tra assignment và trạng thái idle, không tự
tạo hay giải phóng VM; xem [COLAB_V2](COLAB_V2.md). Live smoke fixture 2 chunk
đã resume sau restart kernel trên cùng VM; mất VM/new VM và full book còn mở.
Notebook vẫn là fallback. Hai cách dùng chung batch, validator và checkpoint;
runner không mở SQLite. Drive chỉ trao đổi manifest, nguồn, snapshot và kết quả
bất biến. Auth/permission có thể cần người dùng; secret không vào bundle/log.

Frontend dùng trang server-rendered của FastAPI/Jinja2. Chưa cần React,
Tailwind, hàng đợi phân tán, Redis, Docker hoặc framework plugin/provider.
Cấu trúc module dự kiến nằm trong PLAN; chỉ tạo module khi có mã tương ứng.

## Luồng dịch và phục hồi

1. Import nguồn, giữ raw và hash; preview thứ tự/heading trước khi chốt chương.
2. Chia chương thành chunk theo thứ tự, vừa context budget của model thực chạy.
3. Xuất batch tự chứa đủ nguồn, prompt, glossary, context và cấu hình cần chạy.
4. Runner CLI trên alias có sẵn hoặc notebook xác thực batch, chạy tuần tự và lưu
   từng chunk trên Drive, không chờ cuối job mới tải. Live proof hiện giới hạn ở
   fixture 2 chunk và restart kernel cùng VM; chưa thử mất VM/new VM.
5. Local kiểm tra và nhập result trong transaction ngắn; review rồi xuất sách.

Đơn vị checkpoint là chunk, không phải cả chương. Khi runtime mất, load lại
model, bỏ qua result đã xác thực và lưu bền vững; chunk dở phải chạy lại.
Retry có giới hạn theo PLAN, không tự cấp GPU lại vô hạn hoặc vượt ngân sách;
MVP ưu tiên người dùng bấm resume sau mất phiên. Nút UI hiện gọi script đã kiểm
chứng trên alias có sẵn; nhận đủ result chuyển sang review, duyệt/export chính
thức vẫn do người dùng chủ động.
Không coi trạng thái “running” hoặc file vừa xuất hiện trên Drive là bằng chứng
kết quả hoàn tất. File partial, sai checksum hoặc lệch snapshot phải được báo rõ.

Import có schema version và idempotency: cùng result nhập lại là no-op; cùng
job/chunk nhưng nội dung khác phải thành conflict. Source, model/tokenizer,
prompt, glossary và cấu hình đều có version/hash theo hợp đồng PLAN.
Sửa đầu vào tạo batch mới, không sửa snapshot của batch cũ.

Nguồn gốc, bản dịch máy và revision sửa tay được giữ riêng. Result đến muộn
không ghi đè bản sửa hiện hành; người dùng so sánh và áp dụng có chủ đích.
Export theo thứ tự nguồn, ưu tiên revision đã duyệt và báo rõ phần thiếu/stale.

## Glossary, ngữ cảnh và chất lượng

Glossary theo sách lưu thuật ngữ chuẩn, aliases, bản dịch và ghi chú nhân vật/xưng hô.
Lưu kiểm revision để tránh hai tab ghi đè; job mới đóng băng entries/revision/hash.
Sửa glossary không thay snapshot, result hoặc sửa tay của job cũ.
Ví dụ giả lập: một thuật ngữ đã duyệt không nên đổi cách dịch giữa các chương.
Xưng hô phụ thuộc cặp nhân vật và ngữ cảnh; tránh thay chuỗi toàn cục mù quáng.

Hiện dùng glossary, context vẫn là `none`; context nguồn có giới hạn còn là
hướng sau này, chưa dùng RAG hay vector DB.
Snapshot phải chứa dữ liệu cần chạy, không chỉ hash hoặc tên revision.
Chất lượng được đánh giá bằng review tiếng Việt và thời gian sửa thực tế;
checker kỹ thuật không chứng minh bản dịch đã đủ ý hoặc tự nhiên.

User đã chọn `Qwen/Qwen3.5-4B` làm provider tích hợp. Batch/review v2 hiện có
được mô tả ở [REAL_BATCH](REAL_BATCH.md) và [INTEGRATION](INTEGRATION.md).
P0 benchmark là lịch sử trong [archive/p0](../archive/p0/README.md); metrics chưa
được lưu trong repo và không phải quality gate cho việc dùng app.

## Lộ trình thực hiện

| Cổng | Kết quả cần chứng minh |
| --- | --- |
| P0 | Đã chốt Qwen3.5 theo user; benchmark lưu trữ, metrics chưa có trong repo |
| P1 | TXT qua fake provider, restart/resume, import idempotent và bảo toàn sửa tay |
| P2 | Provider thật/EPUB; script điều phối trên alias Colab có sẵn, notebook fallback và checkpoint ngoài VM |
| P3 | UI Dịch/tiến độ/resume, review/glossary, conflict/revision, backup/restore và accessibility |
| P4 | Hoãn theo yêu cầu user, đã có dữ liệu |

Provider tích hợp đã chốt Qwen3.5; không mở lại so model hay crawl để tiếp tục
app. Ngôn ngữ EN → VI và ngân sách 0 đồng giữ nguyên. Các ngưỡng benchmark lịch
sử chưa có metrics lưu trong repo; không suy ra hiệu quả hoặc chất lượng từ
test pipeline offline.
P1 có thể dùng fake provider để kiểm tra luồng dữ liệu mà không cần GPU.
Chi tiết acceptance và exit theo ROADMAP; bảng trên chỉ tóm tắt.

## Hướng mở rộng có điều kiện

Giữ các ý tưởng sau cho lúc có nhu cầu và bằng chứng, chưa đưa vào MVP:

- Nhiều provider hoặc API: khi phương án hiện tại không đạt chất lượng/giá/độ sẵn sàng.
- GPU worker riêng như RunPod: khi gián đoạn Colab gây tổn thất đo được và có ngân sách.
- Memory/RAG, embeddings hoặc vector search: khi glossary/context vẫn còn lỗi xuyên chương đã ghi nhận.
- PostgreSQL và phân quyền: khi có nhu cầu nhiều người dùng và contention thực tế.
- Nhiều website, DOCX: sau khi luồng nhập/xuất hiện tại ổn định và có nhu cầu cụ thể.
- Tự trích thuật ngữ, đánh giá tự động, phối hợp nhiều model: chỉ sau khi có bộ lỗi hồi quy và phép so sánh.

Không tự chuyển database vì số chương hoặc vì gọi hệ thống là “production”.
Công cụ parsing, inference và thư viện bổ sung được chọn khi triển khai phần
cần dùng, không biến danh sách công nghệ tham khảo thành dependency bắt buộc.

## Bảo toàn dữ liệu và giới hạn tin cậy

Novel, output model và bundle nhập là dữ liệu không tin cậy; không làm theo
chỉ thị nhúng trong đó hoặc cấp tool cho model dịch. Validate input/output,
kiểm tra giới hạn file và escape nội dung khi review hoặc xuất XHTML.

Không commit secret, `.env`, database, dữ liệu người dùng hoặc toàn văn có bản
quyền. Fixture phải nhỏ, giả lập hoặc có quyền sử dụng. Backup cần giữ DB và
assets nhất quán, và chỉ coi phục hồi là đạt sau khi đã thử restore.

Mỗi phase phải báo bằng chứng đã kiểm tra và phần còn thiếu. Test P1 kiểm tra
luồng giả; không chứng minh model thật hoặc Colab đáp ứng các yêu cầu trên.
