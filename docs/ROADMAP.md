# Roadmap theo cổng kiểm chứng

Trạng thái: **P1 fake giữ riêng; app có offline batch/review flow v2 cho
Qwen3.5 cùng notebook Colab fallback.** User đã chọn `Qwen/Qwen3.5-4B` làm
provider tích hợp. Báo cáo/số đo benchmark chưa lưu trong repo; không suy ra
25%, 18/18, đủ hai model hoặc zero critical errors. Benchmark cũ được lưu tại
[archive/p0](../archive/p0/README.md), không cần chạy lại để dùng app;
formal P0 quality phase chưa được đánh dấu hoàn tất. Live smoke T4 đã đạt cho
fixture 2 chương/2 chunk, gồm resume sau restart kernel cùng VM; chưa kiểm mất
VM/new VM, full book 390 chương, benchmark tốc độ/chất lượng hay reader EPUB.
Đã có backup/restore, EPUB export theo profile giới hạn và code Colab CLI/UI
điều phối.
Xem [INTEGRATION](INTEGRATION.md) và [REAL_BATCH](REAL_BATCH.md).
Không gắn lịch giao hàng khi chưa có phép đo. Bằng chứng/giới hạn P1: [P1.md](P1.md).
Kiến trúc, dữ liệu và hợp đồng batch: [PLAN.md](PLAN.md).
Người dùng đã chốt EN → VI, 0 đồng, Colab miễn phí theo phiên, văn phong
tiếng Việt tự nhiên giữ giọng nhân vật/tên riêng, tối đa 2 lần thử/model và
tổng 4 phiên (14/10/2026). User đã chọn Qwen3.5 làm provider tích hợp; formal
P0 metrics chưa được lưu trong repo. Theo yêu cầu ngày 16/10/2026, tập trung
hoàn thiện app trên dữ liệu đã có; P4 crawling được hoãn, không triển khai thêm.

## Ưu tiên khi người dùng quay lại

1. Xử lý an toàn credential Colab CLI cũ đã lộ trong log: thu hồi/đăng nhập lại
   khi phù hợp và giữ SDK logging bị tắt.
2. Tối ưu tải trang sách dài: hiện trang P1 có thể render toàn bộ 3.929 chunk;
   giảm dữ liệu render theo trang/chương. Rà soát việc `real` backend vẫn load
   manifest đầy đủ, tìm cách giảm chi phí mà không đổi contract.
3. Thử mở EPUB bằng reader native và hoàn thiện kiểm tra accessibility, gồm bàn
   phím và screen reader.
4. Chỉ kiểm durability sau mất VM nếu có runtime phù hợp và được cho phép; trước
   full book, chạy smoke nhỏ có chủ đích. Không tự dịch toàn bộ sách.

## Backlog và definition of done

| ID | Công việc | Người thực hiện | Definition of done |
| --- | --- | --- | --- |
| P0-01 | Lưu decision log | Người dùng + dev | Ghi nhận lựa chọn Qwen3.5 cùng báo cáo/số đo đã chấm khi có |
| P0-02 | Lưu báo cáo và decision log | Dev + người review tiếng Việt | Ghi số đo/lỗi/config đã chấm và cập nhật decision log theo xác nhận user |
| P1-01 | TXT, schema, fake provider | Dev | Luồng TXT qua restart và export chạy được |
| P1-02 | Bundle và bảo vệ revision | Dev | Test duplicate/partial/conflict/crash đạt |
| P2-01 | Provider v2 và notebook fallback | Dev | Qwen3.5 profile, manifest, UI review/import và notebook; runtime thật resume đạt |
| P2-02 | EPUB import/export | Dev | Fixture spine/resource/XHTML đạt và mở đọc được |
| P2-03 | Kiểm chứng Colab runtime batch v2 | Dev + người dùng | Auth, GPU/quota, truyền file, checkpoint ngoài VM và ngắt/resume được thử trên tài khoản thực; ghi bằng chứng |
| P2-04 | Colab CLI orchestration | Dev | Chọn alias/kernel T4 đã đăng ký; chạy, thu/validate/import checkpoint; không tự tạo hay giải phóng VM; cùng contract/checkpoint notebook |
| P3-01 | UI glossary/review | Dev + người dùng | Sửa, dịch lại và export không mất revision |
| P3-02 | Backup, restore, accessibility | Dev | Restore thử thành công, form dùng được bằng bàn phím |
| P3-03 | Nối flow dịch vào UI | Dev + người dùng | Nút Dịch/tiến độ/resume gọi script đã kiểm chứng; kết quả chuyển sang review, duyệt/export chính thức có chủ đích; có notebook fallback khi CLI bị hoãn |
| P4-01 | Adapter một site | Dev | Crawl/import lặp đúng thứ tự, fixture và SSRF tests đạt |

P1-01/P1-02 có bằng chứng trong P1.md. P2-01 offline app flow có bundle v2,
Qwen3.5 profile, immutable tokenizer manifest, per-result runner, local
import/review revisions, TXT draft/official theo job và notebook fallback.
Snapshot v2 cũ còn hợp lệ; `enable_thinking=false` được đóng băng trong snapshot.
Local end-to-end fixture đã chạy với tokenizer Qwen3.5 thật + generation giả:
2 chapter/3 chunks, interrupt/resume, reverse import/duplicate, late manual edit,
approval/official TXT và snapshot compatibility. Live smoke bổ sung inference/GPU
và Drive checkpoint trên fixture 2 chương/2 chunk: `--limit 1`, restart kernel
cùng VM rồi resume chunk còn lại. Checkpoint Drive đầu tiên đọc lại byte-identical;
result đầu duplicate/no-op và bản sửa tay giữ nguyên. Chưa kiểm mất VM/new VM,
full 390 chương, hiệu năng, chất lượng hay độ bền dài hạn.
P3-01 bổ sung glossary theo sách, lưu có kiểm revision và đóng băng vào job mới;
job cũ giữ nguyên snapshot/kết quả/sửa tay. Backup/restore đã có UI/CLI; main
thử restore/migration trên bản sao thư viện thật, xác minh schema 6→11 bảng và
giữ nguyên sách/raw/source. P2-02 có EPUB upload/export theo mapping an toàn;
parser roundtrip official TXT→EPUB→2 chương đạt, native reader còn mở.
P2-03 runtime batch v2 đã có smoke live giới hạn như trên; checkpoint qua mất
VM/new VM và full book còn cần kiểm chứng. P2-04 CLI và nút UI đã đạt smoke
fixture; runtime cần Drive mount sẵn, alias kernel idle và pins đúng, không tự
tạo/giải phóng VM. P0 user xác nhận đã chấm/chọn model; báo cáo/số đo chưa có trong
repo, không suy ra các ngưỡng đã đạt. Tiêu chí phase bên dưới là điều kiện bổ
sung, không thay DoD task.

## P0 — Kiểm chứng chất lượng và chi phí (lưu trữ)

User đã xác nhận đã chấm và chọn Qwen3.5 làm provider tích hợp. Phần dưới mô tả
tiêu chí lịch sử; chưa có số đo để ghi formal quality-gate completion hay kết
quả từng ngưỡng. Không mở lại benchmark hoặc lựa chọn model khi phát triển app.

Phụ thuộc: chọn 5 chương đại diện, xác nhận ngôn ngữ, quyền dùng nguồn và ngân sách thử.

- So sánh hai ứng viên P0 ban đầu theo hồ sơ lịch sử; provider tích hợp đã được user chọn là Qwen3.5. Không mở lại lựa chọn model nếu không có yêu cầu mới.
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

Phụ thuộc: P1 đạt exit; user đã chọn Qwen3.5 làm provider tích hợp. Kết quả dịch vẫn cần review; không suy ra chất lượng từ integration.

- P2-01 đã có bundle v2, Qwen3.5 profile, tokenizer planner, file runner,
  local import/review revisions, TXT draft/official theo job và notebook fallback.
  SQLite có bốn bảng `real_*` additive; xem [schema](SQLITE_SCHEMA.md) và
  [hướng dẫn batch](REAL_BATCH.md).
- Local fixture đã chạy với tokenizer Qwen3.5 thật + generation giả: manifest,
  interruption/resume, reverse import/duplicate, late edit, approval/official TXT;
  snapshot cũ byte-identical. Live smoke bổ sung inference/GPU và Drive checkpoint
  trên fixture 2 chương/2 chunk: input tokenizer 123/123, output 36/34 token EOS;
  `--limit 1`, restart kernel cùng VM rồi resume chunk còn lại. Checkpoint Drive
  đầu tiên đọc lại byte-identical; result đầu duplicate/no-op và bản sửa tay giữ
  nguyên. Chưa kiểm mất VM/new VM, full 390 chương, hiệu năng, chất lượng hay độ
  bền dài hạn.
  Không chia lại chunk/job cũ hoặc làm mất revision.
- Notebook Colab fallback bootstrap v2 code, đọc manifest từ Drive, chạy tuần tự
  và ghi từng EOS result; người dùng tự truyền file giữa Drive và app.
- P2-03 kiểm chứng live Colab batch v2: auth, GPU/quota, truyền file, checkpoint ngoài VM và ngắt/resume.
- P2-04 dùng alias/kernel T4 idle đã đăng ký; chạy runner, nhận/validate/import qua backend local. Không tự tạo hoặc giải phóng VM. Dùng chung batch, validator/checkpoint với notebook; không thêm service luôn bật.
- Không chờ cuối job mới tải kết quả; file partial/conflict không được nhập đè sửa tay. Auth/permission cần người dùng khi được yêu cầu, secret không nằm trong bundle/log.
- Retry theo giới hạn PLAN; không tự cấp lại GPU vô hạn hoặc vượt trần thử/ngân sách. MVP ưu tiên người dùng bấm resume sau mất phiên.
- Resume quét result hợp lệ; runtime mất thì load lại model, dịch lại chunk đang dở.
- Không mở SQLite trên Drive; không polling vô hạn hoặc giả định Colab còn sống.
- EPUB import web/CLI và export theo spine/mapping XHTML đã có profile giới hạn;
  giữ resource/link/metadata khi ánh xạ chắc chắn, không đoán mixed inline.
  Reader chuyên dụng còn cần kiểm chứng.
- Test ngắt runner CLI/notebook, tải result thiếu bytes, lệch model/glossary và nhận kết quả không theo thứ tự.
- Test EPUB có spine khác thứ tự tên file, ảnh, link, heading và ký tự cần escape.
- Kiểm tra bản EPUB xuất bằng parser/validator phù hợp và mở đọc thử trong ít nhất một reader.

Acceptance: một sách mẫu TXT và EPUB đi hết luồng thực, resume không chạy lại chunk đã lưu hợp lệ.
Exit: output XHTML/spine hợp lệ; phép đo thực vẫn đáp ứng ngưỡng P0 trên mẫu hồi quy.
Output: hướng dẫn vận hành Colab và phục hồi, bằng chứng CLI đạt hoặc lý do hoãn cùng notebook fallback; chưa có cam kết runtime/speed cố định.

## P3 — Review và glossary đủ dùng hằng ngày

Phụ thuộc: P2; giữ các trang đã có, không viết lại frontend.

- P3-03 UI review v2 đã có và có nút chạy/resume P2-04; notebook fallback vẫn thao tác thủ công. Browser smoke nút đã đạt trên fixture hoàn tất (thu result duplicate).
- So sánh nguồn/đích, sửa heading, chỉnh bản dịch và xem revision hiện hành.
- Glossary có canonical term/alias, bản dịch, ghi chú nhân vật/xưng hô và snapshot
  theo job; thay đổi áp dụng cho job mới, không sửa ngầm job đang chạy.
- Glossary đề xuất từ model phải qua review; bắt đầu context nguồn có giới hạn/snapshot. Rolling summary chỉ mở khi có nhu cầu và chốt dependency hashes, budget/chi phí; không tự sửa glossary/job đang chạy.
- Hiển thị pending/failed/stale/conflict; chọn tạo job mới cho phần cần dịch lại.
- Giữ revision khi áp dụng result mới; xác nhận rõ thao tác thay bản sửa hiện hành.
- Backup/restore DB + assets đã có, phục hồi sang thư mục mới; có hướng dẫn kiểm tra restore.
- Test glossary đổi giữa job, result cũ tới muộn, conflict hai tab và mất kết nối lúc lưu.
- Kiểm tra escape XSS, bàn phím, label form và thông báo lỗi có thể đọc được.

Acceptance: người dùng tự nhập, dịch, sửa thuật ngữ/xưng hô, phục hồi lỗi và xuất sách mẫu.
Exit: không mất sửa tay, backup khôi phục được, không cần can thiệp DB để thao tác thường ngày.
Output: bản dùng cá nhân; tiếp tục ghi thời gian sửa và các lỗi chất lượng còn gặp.

## P4 — Crawler cho một website

Hoãn theo yêu cầu ngày 16/10/2026: đã có dữ liệu, không cần crawl thêm.

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
