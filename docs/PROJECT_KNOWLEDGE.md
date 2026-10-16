# Tổng quan dự án Novel Translate

## Trạng thái và cách đọc

Repo có ứng dụng local P1 và test với provider giả; đang chuẩn bị P0 bằng
notebook tự chứa mã, chưa có provider thật trong app hoặc kết quả benchmark.
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

Xây dựng công cụ cá nhân hỗ trợ nhập tiểu thuyết, tách chương, dịch bằng LLM,
review/sửa bản dịch và xuất sách tiếng Việt. Người dùng đã xác nhận EN → VI,
ngân sách 0 đồng, Colab miễn phí theo phiên, văn phong tiếng Việt tự nhiên giữ
giọng nhân vật/tên riêng, tối đa 2 lần thử/model và tổng 4 phiên ngày 14/10/2026.

Giá trị mong muốn là giảm thời gian dịch và sửa mà vẫn giữ nghĩa, tên riêng,
thuật ngữ, tính cách và xưng hô nhất quán. Giữ bản gốc và sửa tay là yêu cầu
bắt buộc; bản dịch máy luôn cần kiểm tra, nhất là thiếu đoạn hoặc sai ý.

Phạm vi ban đầu là một người dùng: TXT trước, EPUB sau, glossary và review đủ
dùng. Mục tiêu rộng hơn vẫn gồm crawler, các nguồn nhập khác và bộ nhớ xuyên
chương, nhưng chỉ mở rộng qua các cổng trong ROADMAP.

## Kiến trúc đã chọn cho bản đầu

```text
Trình duyệt → FastAPI + Jinja2 → SQLite và dữ liệu sách local
                                  ↓ xuất batch bất biến
                         Drive: manifest + source + snapshots
                                  ↓ runner CLI (sau kiểm chứng) / notebook
                         Colab → model → result từng chunk
                                  ↓ nhập và kiểm tra ở local
                         Review → TXT/EPUB
```

Máy Dell Vostro giữ giao diện, nguồn sách, database và trạng thái ứng dụng.
Đã xác nhận dùng WSL; RAM, distro, Python và dung lượng chưa xác nhận. Không
suy ra khả năng chạy model hay trần dung lượng từ tên thiết bị. Backend local là nơi duy nhất truy cập SQLite.

Colab xử lý batch bằng file theo phiên, không phải backend luôn bật. P2-03 dự kiến
kiểm chứng Colab CLI trên WSL/tài khoản thực; chỉ khi đạt mới làm script local
P2-04 điều phối batch → phiên Colab → runner → nhận/validate/import → giải phóng
phiên. CLI là phương án tạm chưa được thử; nếu không đạt thì ghi lý do hoãn và
dùng notebook fallback. Hai cách dùng chung batch, validator và checkpoint;
runner không mở SQLite. Drive chỉ trao đổi manifest, nguồn, snapshot và kết quả
bất biến. Auth/permission có thể cần người dùng; secret không vào bundle/log.

Frontend dùng trang server-rendered của FastAPI/Jinja2. Chưa cần React,
Tailwind, hàng đợi phân tán, Redis, Docker hoặc framework plugin/provider.
Cấu trúc module dự kiến nằm trong PLAN; chỉ tạo module khi có mã tương ứng.

## Luồng dịch và phục hồi

1. Import nguồn, giữ raw và hash; preview thứ tự/heading trước khi chốt chương.
2. Chia chương thành chunk theo thứ tự, vừa context budget của model thực chạy.
3. Xuất batch tự chứa đủ nguồn, prompt, glossary, context và cấu hình cần chạy.
4. Runner CLI (sau kiểm chứng) hoặc notebook xác thực batch, chạy tuần tự và lưu
   bền vững từng chunk ngoài VM (Drive/local), không chờ cuối job mới tải.
5. Local kiểm tra và nhập result trong transaction ngắn; review rồi xuất sách.

Đơn vị checkpoint là chunk, không phải cả chương. Khi runtime mất, load lại
model, bỏ qua result đã xác thực và lưu bền vững; chunk dở phải chạy lại.
Retry có giới hạn theo PLAN, không tự cấp GPU lại vô hạn hoặc vượt ngân sách;
MVP ưu tiên người dùng bấm resume sau mất phiên. P3 nối script đã kiểm chứng
vào nút Dịch/tiến độ/resume; nhận đủ result chuyển sang review, duyệt/export
chính thức vẫn do người dùng chủ động.
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

Glossary lưu thuật ngữ chuẩn, aliases, bản dịch và ghi chú nhân vật/xưng hô.
Ví dụ giả lập: một thuật ngữ đã duyệt không nên đổi cách dịch giữa các chương.
Xưng hô phụ thuộc cặp nhân vật và ngữ cảnh; tránh thay chuỗi toàn cục mù quáng.

MVP dùng glossary và context nguồn có giới hạn, chưa dùng RAG hay vector DB.
Snapshot phải chứa dữ liệu cần chạy, không chỉ hash hoặc tên revision.
Chất lượng được đánh giá bằng review tiếng Việt và thời gian sửa thực tế;
checker kỹ thuật không chứng minh bản dịch đã đủ ý hoặc tự nhiên.

Model chưa được chọn. Hai ứng viên P0 là Qwen3-4B-Instruct-2507 và
Qwen2.5-7B-Instruct; revision và cấu hình ở [P0_MODELS.md](../archive/p0/docs/P0_MODELS.md).
Chưa có bảng xếp hạng chất lượng thực đo. Quyền truy cập, giấy phép, tokenizer,
template, VRAM, context và chi phí phải xác nhận theo ứng viên và môi trường thật.
Các liên kết tham khảo và giới hạn bằng chứng hiện có nằm ở cuối PLAN.

## Lộ trình thực hiện

| Cổng | Kết quả cần chứng minh |
| --- | --- |
| P0 | Benchmark 5 chương × 2 ứng viên theo tiêu chí đã chốt; chưa có kết quả |
| P1 | TXT qua fake provider, restart/resume, import idempotent và bảo toàn sửa tay |
| P2 | Provider thật/EPUB; kiểm chứng CLI trên WSL rồi làm script điều phối, notebook fallback và phục hồi từ checkpoint ngoài VM |
| P3 | UI Dịch/tiến độ/resume, review/glossary, conflict/revision, backup/restore và accessibility |
| P4 | Crawler đúng một website có fixture, kiểm tra truy cập và SSRF |

Bước dịch thật cần qua P0: đã có hai ứng viên, tiêu chí văn phong và trần thử
nghiệm đã chốt, người dùng tự review; đã nhận đủ 5 TXT và upload/xác minh corpus
full trên Drive. Còn xác minh URL ch03–ch05/quyền nguồn và hoàn thành baseline.
Playwright gặp Cloudflare security verification nên mục lục chưa xác minh được.
Ngôn ngữ EN → VI và ngân sách 0 đồng đã chốt. Chưa có phép đo tốc độ,
chi phí hoặc chất lượng model.
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
