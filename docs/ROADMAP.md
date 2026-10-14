# Roadmap theo cổng kiểm chứng

Trạng thái: **P1 có luồng local đã kiểm thử bằng provider giả**, P0 chưa benchmark; P2 có riêng CLI import EPUB theo yêu cầu; export/provider/điều phối và P3–P4 chưa triển khai.
Không gắn lịch giao hàng khi chưa có phép đo. Bằng chứng/giới hạn P1: [P1.md](P1.md).
Kiến trúc, dữ liệu và hợp đồng batch: [PLAN.md](PLAN.md).
Người dùng đã chốt EN → VI, 0 đồng, Colab miễn phí theo phiên, văn phong
tiếng Việt tự nhiên giữ giọng nhân vật/tên riêng, tối đa 2 lần thử/model và
tổng 4 phiên (14/10/2026). P1 dùng fake provider; P0 chưa benchmark.

## Backlog và definition of done

| ID | Công việc | Người thực hiện | Definition of done |
| --- | --- | --- | --- |
| P0-01 | Chốt mẫu, ngưỡng và ứng viên | Người dùng + dev | Có 5 chương, hai ứng viên và ngưỡng ghi trước khi chấm |
| P0-02 | Chạy và chấm benchmark | Dev + người review tiếng Việt | Điền bảng PLAN, ghi lỗi/config, ra quyết định go/no-go |
| P1-01 | TXT, schema, fake provider | Dev | Luồng TXT qua restart và export chạy được |
| P1-02 | Bundle và bảo vệ revision | Dev | Test duplicate/partial/conflict/crash đạt |
| P2-01 | Notebook và provider thật | Dev | Ngắt runtime rồi resume từ result bền vững thành công |
| P2-02 | EPUB import/export | Dev | Fixture spine/resource/XHTML đạt và mở đọc được |
| P2-03 | Kiểm chứng Colab CLI trên WSL | Dev + người dùng | Auth, GPU/quota, truyền file, checkpoint ngoài VM và ngắt/resume được thử trên tài khoản thực; ghi bằng chứng hoặc lý do hoãn CLI và dùng notebook |
| P2-04 | Script local điều phối Colab | Dev | Sau khi P2-03 đạt: batch → phiên Colab → runner → nhận/validate/import qua backend local → giải phóng phiên; chung hợp đồng/checkpoint với notebook, bảo toàn revision |
| P3-01 | UI glossary/review | Dev + người dùng | Sửa, dịch lại và export không mất revision |
| P3-02 | Backup, restore, accessibility | Dev | Restore thử thành công, form dùng được bằng bàn phím |
| P3-03 | Nối flow dịch vào UI | Dev + người dùng | Nút Dịch/tiến độ/resume gọi script đã kiểm chứng; kết quả chuyển sang review, duyệt/export chính thức có chủ đích; có notebook fallback khi CLI bị hoãn |
| P4-01 | Adapter một site | Dev | Crawl/import lặp đúng thứ tự, fixture và SSRF tests đạt |

P1-01/P1-02 có bằng chứng trong P1.md; P2-02 mới có phần import CLI theo
yêu cầu ngày 14/10/2026 (xem EPUB_IMPORT.md), chưa đạt DoD export/reader.
Các cổng P0/provider/CLI Colab vẫn chưa đạt. Tiêu chí phase
bên dưới là điều kiện bổ sung, không thay thế DoD của task.

## P0 — Kiểm chứng chất lượng và chi phí

Phụ thuộc: chọn 5 chương đại diện, xác nhận ngôn ngữ, quyền dùng nguồn và ngân sách thử.

- Chọn hai ứng viên model; có thể thử thêm một công cụ có sẵn nếu cài/chạy phù hợp.
- Cùng nguồn và quy tắc chấm; ghi khác biệt prompt/template/tokenizer bắt buộc của mỗi model.
- Ghi phiên bản, phần cứng, lượng tử hóa, token vào/ra, thời gian load, dịch và sửa tay.
- Với chạy local/Colab, ghi thời gian GPU và chi phí thực nếu có; không quy đổi thành giá bịa.
- Chấm lỗi thiếu/thêm ý, tên riêng, xưng hô, đối thoại; lưu ví dụ lỗi và bản sửa.
- Đo baseline sửa/dịch thủ công trên mẫu để biết công cụ thực sự tiết kiệm thời gian hay không.
- Ngưỡng đã chốt: không bỏ đoạn; mọi chunk hoàn tất; không lỗi sai ý trọng yếu còn sót sau review.
- Hiệu quả đã chốt: tổng thời gian dịch + sửa giảm ít nhất 25% so với baseline trên cùng mẫu.
- Văn phong đã chốt: tiếng Việt tự nhiên, giữ giọng nhân vật và tên riêng; tối đa 2 lần thử/model, tổng 4 phiên Colab miễn phí. Chưa có kết quả benchmark.
- Kiểm tra chương dài bằng chunk đúng context budget, không chỉ benchmark đoạn ngắn vừa model.

Acceptance: báo cáo có 5 chương × 2 ứng viên, số liệu thực, cấu hình tái chạy và lỗi đại diện.
Exit: chọn model/phương án đạt ngưỡng đã chốt; không đạt thì đổi ứng viên hoặc dừng đầu tư phần dịch.
Output: báo cáo benchmark và decision log; chưa tuyên bố sản phẩm dùng được.

## P1 — Một luồng TXT chạy bền vững với fake provider

Phụ thuộc: schema và hợp đồng snapshot của PLAN; không cần GPU để bắt đầu.

- Dựng FastAPI, SQLite local, trang nhập sách và xem chương tối thiểu.
- Import TXT, preview heading/order, chunk theo thứ tự và lưu nguồn bất biến.
- Fake provider trả đầu ra xác định; tạo/export batch và import result qua cùng validator dự kiến.
- Lưu job/result/revision; export TXT theo thứ tự và thông báo phần thiếu.
- Hoàn thành idempotency, checksum, transaction/checkpoint trước khi nối model thật.
- Test restart giữa job, crash giữa import, import trùng, file partial, input hash lệch và payload xung đột.
- Test result tới chậm sau sửa tay, hai tab sửa cùng base revision và xuất nháp khi thiếu chunk.

Acceptance: nhập một TXT → dịch giả → restart → nhận tiếp result → sửa → xuất đúng thứ tự.
Exit: không mất source/sửa tay, không nhân kết quả khi import lại, lỗi được nhìn thấy và có cách tiếp tục.
Output: vertical slice có kiểm thử; chưa đánh giá chất lượng dịch thật.

## P2 — EPUB và Colab runner với provider thật

Phụ thuộc: P1 đạt exit; chọn provider qua P0 trước khi coi kết quả dịch là được chấp nhận.

- Nối model/tokenizer/template thực, đo context budget và xác thực provenance.
- P2-01 thống nhất bundle app/Colab trước, rồi planner theo tokenizer với job snapshot bất biến; không chia lại chunk cũ làm mất revision. Mapping/migration và test cần chốt khi nối provider thật; xem [ghi chú schema](SQLITE_SCHEMA.md).
- Notebook đọc manifest từ Drive, chạy tuần tự, ghi bền vững từng result hoàn tất ngoài VM và báo lỗi rõ; giữ làm fallback.
- P2-03 kiểm chứng CLI trên WSL/tài khoản thực: auth tương tác, quyền truy cập, GPU/quota, truyền file, lưu result ngoài VM và ngắt/resume. Đây là phương án tạm, chưa được thử; nếu không đạt thì ghi lý do hoãn và tiếp tục notebook.
- P2-04 phụ thuộc P2-03 đạt: script local theo yêu cầu xuất batch, tạo phiên, chạy runner, nhận/validate/import qua backend local và giải phóng phiên. Dùng chung batch, validator/checkpoint với notebook; không thêm service luôn bật.
- Không chờ cuối job mới tải kết quả; file partial/conflict không được nhập đè sửa tay. Auth/permission cần người dùng khi được yêu cầu, secret không nằm trong bundle/log.
- Retry theo giới hạn PLAN; không tự cấp lại GPU vô hạn hoặc vượt trần thử/ngân sách. MVP ưu tiên người dùng bấm resume sau mất phiên.
- Resume quét result hợp lệ; runtime mất thì load lại model, dịch lại chunk đang dở.
- Không mở SQLite trên Drive; không polling vô hạn hoặc giả định Colab còn sống.
- Thêm EPUB import/export theo spine và mapping XHTML; giữ resource/link/metadata.
- Test ngắt runner CLI/notebook, tải result thiếu bytes, lệch model/glossary và nhận kết quả không theo thứ tự.
- Test EPUB có spine khác thứ tự tên file, ảnh, link, heading và ký tự cần escape.
- Kiểm tra bản EPUB xuất bằng parser/validator phù hợp và mở đọc thử trong ít nhất một reader.

Acceptance: một sách mẫu TXT và EPUB đi hết luồng thực, resume không chạy lại chunk đã lưu hợp lệ.
Exit: output XHTML/spine hợp lệ; phép đo thực vẫn đáp ứng ngưỡng P0 trên mẫu hồi quy.
Output: hướng dẫn vận hành Colab và phục hồi, bằng chứng CLI đạt hoặc lý do hoãn cùng notebook fallback; chưa có cam kết runtime/speed cố định.

## P3 — Review và glossary đủ dùng hằng ngày

Phụ thuộc: P2; giữ các trang đã có, không viết lại frontend.

- P3-03 nối script P2-04 đã kiểm chứng vào nút Dịch, tiến độ và resume; khi nhận đủ result thì chuyển sang review. Nếu CLI hoãn, giữ flow notebook; review/duyệt/export chính thức vẫn có chủ đích.
- So sánh nguồn/đích, sửa heading, chỉnh bản dịch và xem revision hiện hành.
- Thêm canonical term/alias, ghi chú nhân vật/xưng hô và snapshot glossary.
- Glossary đề xuất từ model phải qua review; bắt đầu context nguồn có giới hạn/snapshot. Rolling summary chỉ mở khi có nhu cầu và chốt dependency hashes, budget/chi phí; không tự sửa glossary/job đang chạy.
- Hiển thị pending/failed/stale/conflict; chọn tạo job mới cho phần cần dịch lại.
- Giữ revision khi áp dụng result mới; xác nhận rõ thao tác thay bản sửa hiện hành.
- Thêm backup/restore DB + assets và hướng dẫn kiểm tra restore.
- Test glossary đổi giữa job, result cũ tới muộn, conflict hai tab và mất kết nối lúc lưu.
- Kiểm tra escape XSS, bàn phím, label form và thông báo lỗi có thể đọc được.

Acceptance: người dùng tự nhập, dịch, sửa thuật ngữ/xưng hô, phục hồi lỗi và xuất sách mẫu.
Exit: không mất sửa tay, backup khôi phục được, không cần can thiệp DB để thao tác thường ngày.
Output: bản dùng cá nhân; tiếp tục ghi thời gian sửa và các lỗi chất lượng còn gặp.

## P4 — Crawler cho một website

Phụ thuộc: P3 và URL cụ thể; xác nhận điều kiện truy cập trước triển khai adapter.

- Viết adapter đúng một site, lấy mục lục và nội dung theo thứ tự đã preview.
- Tái dùng pipeline import; lưu source URL/hash, tránh tạo lại chương khi crawl trùng.
- Tôn trọng điều kiện website, robots/rate limit và quyền sử dụng nội dung; không vượt cơ chế truy cập.
- Giới hạn tải, timeout, allowlist, kiểm tra redirect/DNS và chặn địa chỉ mạng nội bộ.
- Test HTML fixture thiếu chương/trùng link, thay layout, redirect ngoài site và SSRF.
- Khi site đổi cấu trúc, dừng và báo lỗi; không nhập âm thầm nội dung rỗng hoặc trang đăng nhập.

Acceptance: crawl bộ chương mẫu đúng thứ tự và import lại không nhân dữ liệu.
Exit: review đủ nội dung, lỗi truy cập/layout rõ ràng, kiểm thử trust boundary đạt.
Output: một adapter có fixture; không tuyên bố hỗ trợ mọi website.

## Cổng mở rộng sau MVP

| Mở rộng | Chỉ làm khi có bằng chứng | Điều kiện trước khi mở |
| --- | --- | --- |
| Nhiều provider/API | Provider hiện tại không đạt chất lượng, giá hoặc độ sẵn sàng | So sánh cùng mẫu, hợp đồng lỗi/token/chi phí và secret rõ |
| GPU worker riêng | Colab ngắt phiên gây tổn thất đo được, có ngân sách máy chạy bền | Lease/heartbeat, timeout, idempotency, xử lý worker chết |
| Memory/RAG | Glossary + context hiện tại vẫn có lỗi xuyên chương được ghi nhận | Bộ lỗi hồi quy, so chất lượng/latency/chi phí trước-sau |
| DOCX | Có nhu cầu xuất DOCX cụ thể sau khi TXT/EPUB ổn định | Chốt mapping nội dung/định dạng và fixture kiểm tra, không thuộc MVP |
| Nhiều website | Adapter đầu dùng ổn và có site thứ hai cụ thể | Fixture/điều kiện truy cập riêng; chỉ tách phần thực sự dùng chung |
| Nhiều người dùng/Postgres | Có người dùng đồng thời và nhu cầu phân quyền thực | Auth, isolation dữ liệu, migration/backup, đo contention |

Không thêm lease cho runner batch CLI/notebook theo yêu cầu; chỉ thêm khi có worker riêng nhận việc tự động.
Không chuyển Postgres chỉ vì số chương lớn nếu SQLite local vẫn đáp ứng phép đo.
Mỗi mở rộng cần acceptance riêng và không được làm hỏng invariant source/snapshot/revision.

## Việc cần chốt trước từng cổng

- Trước P0: ngôn ngữ, 5 chương, hai ứng viên, chất lượng mong muốn và trần thử nghiệm đã chốt; đã nhận đủ 5 TXT và upload/xác minh corpus full trên Drive; còn xác minh URL ch03–ch05/quyền nguồn và baseline.
- Trước P1 chạy trên máy thật: RAM/distro WSL/Python/dung lượng, vị trí data và backup.
- Trước P2: model revision, tokenizer/template, quyền truy cập và giới hạn Colab thực tế.
- Trước P4: website cụ thể, phạm vi chương và quyền truy cập hợp lệ.
- Sau mỗi phase: ghi bằng chứng đạt/chưa đạt; chưa đạt thì sửa hoặc đổi quyết định, không tự mở phase tiếp.
