# Đối chiếu hướng sản phẩm — 17/10/2026

Repo hiện làm gì: ứng dụng một người dùng lưu truyện/SQLite local, tạo batch
dịch Qwen3.5 trên Colab, nhập kết quả rồi review/sửa/xuất sách. Đánh giá này lấy
nhu cầu mới nhất của user làm chuẩn: phần lớn thời gian dùng để đọc raw và bản
dịch; Colab dịch qua các phiên; review và glossary giúp cải thiện bản dịch dần.
Giả định tải là một người dùng trên máy local, sách dài hàng trăm chương.

**Kết luận: nền kiến trúc đúng; cần đổi ưu tiên sản phẩm sang việc đọc.** Không
cần viết lại app, bỏ review, đổi model hoặc đổi database. Phiên này chỉ rà soát
và cập nhật kế hoạch; các tính năng reader bên dưới chưa được triển khai.

## Căn cứ và giới hạn

- Đọc WORKFLOW, HANDOFF hiện hành và các mốc lịch sử liên quan, PLAN, ROADMAP,
  PROJECT_KNOWLEDGE, README, INTEGRATION và skill pipeline staging.
- Đối chiếu danh sách/file thay đổi của toàn bộ **25 commit** từ `820cfb7` đến
  `bf59d9a`; đọc thêm diff/mã hiện hành ở các luồng quyết định bên dưới. Đây là
  đánh giá hướng đi qua từng task, không phải kiểm mọi dòng ở mọi revision.
- Lần theo import → source/chunk → batch → runner/checkpoint → import result
  → revision/review → export, cùng routes/templates và các test tương ứng.
- Không đọc/chấm toàn văn sách thật, mở DB người dùng, chạy app/browser hoặc
  dùng Colab/Drive trong lượt này. Live evidence trong HANDOFF là bằng chứng
  lịch sử, không phải phép thử vừa chạy lại.

## Phần đang đi đúng hướng

| Thành phần | Bằng chứng trong code | Giá trị với mục tiêu |
| --- | --- | --- |
| Local nhẹ | [pyproject](../pyproject.toml): bốn dependency app trực tiếp, Colab/tokenizer là extra; [main](../app/main.py) dùng Jinja | Giữ server local và SQLite; chưa có lý do thêm frontend framework hoặc service |
| Đọc raw khi chưa dịch | [get_book](../app/core.py), [book template](../app/templates/book.html) | Nguồn có sẵn dù không có job/result; hiện nằm trong trang P1 review |
| Dịch nhiều phiên | [run_manifest](../app/real_runner.py):23 và [orchestration](../scripts/run_colab.py):629 | Lưu từng chunk, kiểm checkpoint và bỏ qua phần hợp lệ; không buộc GPU luôn bật |
| Đọc kết quả từng phần | [import_real_result](../app/core.py):614, [real_job](../app/templates/real_job.html) | Nhập từng result, job partial vẫn có nội dung hiển thị; notebook cần đưa file về local |
| Review và sửa dần | [save_real_revision](../app/core.py):545, [test revisions](../tests/test_real_store.py):123 | Giữ machine result riêng, chống hai tab ghi đè, bảo toàn sửa tay khi result đến muộn |
| Glossary | [create_real_job](../app/core.py):406, [glossary tests](../tests/test_glossary.py) | Tên/alias/bản dịch/ghi chú xưng hô có revision và snapshot; không đổi ngầm job đang chạy |
| Backup, raw và EPUB | [backups](../app/backups.py), [EPUB parser](../app/epub.py), [export](../app/epub_export.py) | Bảo vệ thư viện cá nhân; giữ profile EPUB giới hạn thay vì xuất mất nội dung |
| Tải theo chương và bàn phím | `d2c5d5c`, `bf59d9a`, [navigation tests](../tests/test_review_navigation.py), [a11y tests](../tests/test_accessibility.py) | Hai task gần nhất phục vụ sách dài và sử dụng local; đáng giữ |

Chưa có phép đo RAM/startup để kết luận app đã nhẹ trên máy thật. Không suy từ
số dependency rằng toàn bộ môi trường cài thêm tokenizer/CLI cũng nhỏ tương tự.

## Những điểm cần điều chỉnh, theo mức ưu tiên

1. **Mục tiêu và backlog đang xoay quanh dịch/review/xuất hơn việc đọc.**
   PLAN ban đầu định nghĩa app là nhập → dịch → sửa → xuất; roadmap P0–P4 không
   có đầu việc riêng cho reader và nhớ chỗ đọc. Vì vậy hoàn thành các task cũ
   vẫn chưa đảm bảo bạn có trải nghiệm đọc hằng ngày.
   Giải pháp: thêm R1/R2 có tiêu chí đọc raw/dịch/song ngữ, đọc tiếp và làm việc
   khi không có Colab. Giữ các phase cũ để tra cứu bằng chứng; dùng backlog mới
   ở [ROADMAP](ROADMAP.md) cho thứ tự triển khai tiếp. Nếu bỏ qua, repo có thể
   tiếp tục hoàn thiện công cụ dịch mà phần dùng thường xuyên vẫn bất tiện.

2. **Nội dung đọc thật vẫn gắn với trang vận hành job và form biên tập.**
   [Trang sách](../app/templates/book.html) đặt real/fake jobs, manifest và
   export trước raw; [trang job](../app/templates/real_job.html) hiển thị bản
   máy trong cột so sánh, bản sửa ở textarea. Đây là UI review dùng được, chưa
   phải reader riêng. Result chưa duyệt đã xem được, nên không có lỗi “bắt
   duyệt mới đọc” trong code hiện tại.
   Giải pháp: thêm trang đọc tái dùng Store, ba chế độ raw/dịch/song ngữ và liên
   kết review đúng đoạn. Dùng bản sửa hiện hành trước bản máy, giữ cảnh báo
   stale/chưa duyệt và chỉ rõ phần thiếu. Đọc không đổi approval; official
   export tiếp tục giữ guard hiện tại. Nếu bỏ qua, đọc dần bản đã sửa còn phải
   đi qua biểu mẫu và các điều khiển dịch không cần dùng trong lúc đọc.

3. **Chưa có trạng thái đọc tiếp độc lập với tiến độ dịch/review.**
   [Route sách](../app/main.py):198 mặc định chương đầu; chương đang xem nằm
   trong URL. Schema trong [Store](../app/core.py):15 và các routes/templates
   chưa có nơi lưu vị trí đọc. Đã đọc đến chương nào khác với đã dịch hay đã
   duyệt đến đâu.
   Giải pháp: R2 lưu một vị trí gần nhất mỗi sách ở SQLite, kèm chapter, chế độ,
   lựa chọn raw/job và anchor hợp lệ nếu có; không cần đồng bộ cloud hoặc vị
   trí từng pixel. Giữ job đọc được chọn tường minh, không tự chuyển sang job
   mới nhất. Nếu bỏ qua, mở lại app sau vài ngày phải tự tìm chương/đoạn cũ.

4. **Dịch qua các phiên đã có cơ chế, bằng chứng mất VM còn thiếu.**
   [Runner](../app/real_runner.py):35–76 kiểm và ghi checkpoint từng chunk;
   HANDOFF chứng minh T4 với hai chunk và restart kernel cùng VM. Điều đó chưa
   chứng minh resume khi VM đã mất và được cấp lại, cũng chưa đo được số phiên
   cần cho một sách. Job hiện chứa toàn sách ([core](../app/core.py):417);
   manifest có trần 16 MiB và 10.000 chunks ([bundles](../app/bundles.py):10,
   [real_bundles](../app/real_bundles.py):26), chưa preflight sách thật.
   Giải pháp: giữ một manifest, dùng limit/resume hiện có; kiểm kích thước plan
   trước GPU, rồi thử VM mới trên fixture nhỏ khi được cấp runtime phù hợp.
   Đọc local và R1/R2 vẫn tiến hành độc lập. Nếu bỏ qua, chưa thể cam kết toàn
   sách hoàn thành trong một/vài phiên hoặc checkpoint bền qua mất VM.

5. **Một số chỉ dẫn tiếp nối và tiêu chí lịch sử có thể kéo việc sang hướng cũ.**
   Trước rà soát, HANDOFF/ROADMAP ưu tiên native EPUB reader/screen reader và
   credential; PLAN/ROADMAP vẫn nhắc ngưỡng benchmark trong exit P2. INTEGRATION
   có câu “accessibility chưa làm” cạnh bằng chứng mới hơn. Kiểm EPUB và screen
   reader vẫn có ích, nhưng chưa cần chặn xây reader local; credential chỉ chặn
   phần Colab cần dùng tới tài khoản.
   Giải pháp: đồng bộ các tài liệu dẫn đường, phân biệt hiện trạng/kế hoạch và
   bằng chứng lịch sử. Giới hạn bốn phiên/hai lần thử mỗi model thuộc benchmark
   P0 lịch sử; không suy thành giới hạn mọi phiên dịch sách. Nếu bỏ qua, phiên
   sau dễ làm đúng task cũ nhưng sai thứ tự giá trị người dùng cần.

Các mục trên là khoảng cách sản phẩm và bằng chứng, không phải kết luận có
mất dữ liệu hoặc cần loại bỏ review. Chưa thấy lý do từ mục tiêu mới để tháo
các cơ chế snapshot, validation, revision, approval export hoặc backup.

## Đối chiếu từng task qua commit

| Commit | Task thực hiện | Đánh giá theo mục tiêu hiện tại |
| --- | --- | --- |
| `820cfb7` | PLAN/ROADMAP/workflow ban đầu | Nền local + Colab đúng; mục tiêu reader chưa được đặt làm chính |
| `0c9af38` | Bổ sung hướng runner/CLI | Hợp lý nếu tùy chọn, không bắt việc đọc phụ thuộc CLI |
| `45fc318` | Core TXT/fake bền vững | Nền kiểm toàn vẹn đúng; fake giữ làm công cụ chẩn đoán |
| `3bec08a` | Web TXT/review và giới hạn request | Dùng được cho review; chưa phải reader hoàn chỉnh |
| `13d5847` | Bằng chứng P1, kế hoạch P0 | Phân biệt fake/quality đúng; giữ benchmark thành lịch sử |
| `3df4761` | Notebook/runner benchmark | Có ích cho chọn model thời điểm đó; không mở lại mặc định |
| `da39e0c` | Chặn checkpoint thiếu output token | Bảo toàn tính đúng đắn; không coi output thiếu là xong |
| `7fe7b1f` | Full corpus benchmark/progress | Phục vụ thử model, chưa chứng minh khả năng dịch full book |
| `261c167` | Nhập EPUB/spine vào SQLite | Sát nhu cầu thư viện đọc raw; đáng giữ |
| `083492a` | Ghi schema/trạng thái | Có ích cho tiếp nối và bảo toàn dữ liệu |
| `5c1a170` | Precision và làm sạch notebook | Sửa lỗi thử model; giữ ở archive sau khi chọn provider |
| `fb997a2` | Batch v2/Store offline | Sát yêu cầu Colab theo phiên, tách khỏi SQLite local |
| `edd1f13` | Qwen3.5 benchmark và CLI | Hợp lý theo lựa chọn user; tránh tiếp tục đầu tư so model |
| `6aff1eb` | Qwen3.5 v2/notebook portable | Phần dịch cần có; dùng cùng contract để resume |
| `fed9f42` | Review/duyệt/TXT theo job | Có giá trị cải thiện dần; approval export không thành điều kiện đọc |
| `7d15aea` | Docs tích hợp và validation | Có bằng chứng; cần đồng bộ các câu readiness cũ |
| `8e48b3a` | Archive benchmark | Đúng hướng thu gọn active app; tên commit không chứng minh quality gate đạt |
| `015b5e8` | Glossary revision/snapshot | Phụ trợ chất lượng phù hợp; giữ sửa tay và job cũ |
| `abc3560` | Backup/restore có kiểm chứng | Cần cho thư viện cá nhân; bảo vệ dữ liệu quan trọng hơn thêm tính năng |
| `169d5d4` | EPUB upload/official export | Hữu ích; profile giới hạn không thay trải nghiệm reader trong app |
| `73ad65e` | Bulk result/review chương | Giảm thao tác nhập/sửa; hỗ trợ đọc dần sau import |
| `cb4323e` | CLI/UI chạy-resume Colab | Tự động hóa đã có; giữ tùy chọn, chưa cần thêm service/worker nền |
| `a85c17e` | Bằng chứng live và handoff | Ghi đúng giới hạn hai chunk/cùng VM; chưa phải full-book proof |
| `d2c5d5c` | Chỉ hydrate chương đang xem | Sát mục tiêu nhẹ trên sách dài; manifest vẫn kiểm đầy đủ |
| `bf59d9a` | Bàn phím/title/nút review | Hợp lý cho sử dụng hằng ngày; screen reader chưa kiểm |

Commit tính năng nhìn chung tách theo task và có test liên quan; một số kết
quả/docs được chốt ở commit bàn giao sau. Không cần sửa lại lịch sử commit.
Phần thiếu là một cổng chấp nhận sản phẩm cho việc đọc, không phải thiếu thêm
công nghệ hoặc thiếu một vòng benchmark.

## Kế hoạch tối thiểu và công cụ phụ trợ

| Thứ tự | Kết quả cần có | Cách kiểm khi triển khai |
| --- | --- | --- |
| R1 | Mở sách → đọc raw/dịch/song ngữ; chọn job; đọc partial và mở review đúng đoạn | Fixture nhiều chương, khác chunking v1/v2, có sửa tay/stale/chưa có result; không cần Colab/tokenizer để đọc nội dung local |
| R2 | Đóng/mở app → đọc tiếp đúng chương/chế độ/job | Restart server cùng data; đổi job không gán anchor nhầm; tiến độ đọc không đổi trạng thái dịch/duyệt |
| R3 | Dịch qua phiên khác bằng manifest/checkpoint cũ | Preflight trước GPU; fixture nhỏ trên VM mới, so hashes, không sinh lại chunk hợp lệ; auth/quota thiếu thì dừng phần live |
| R4 | Đang đọc có thể sửa/review và dùng glossary thuận tiện | Giữ revisions/conflict; sửa glossary không mutate job cũ; kiểm lỗi chất lượng mẫu trước thêm context |

Đã có: glossary tên/alias/ghi chú xưng hô, review song song nguồn/đích, sửa tay
có lịch sử, lọc thiếu/chưa duyệt/đã duyệt, bulk import, backup/restore và export.
Nên làm trước: đọc tiếp và bố cục đọc gọn, độ rộng dòng/cỡ chữ hợp lý.
Tìm trong sách, nhiều bookmark và ghi chú đoạn là các ứng viên sau khi dùng
reader thấy cần; chưa đưa cả danh sách thành tính năng bắt buộc.

Context nguồn có giới hạn từng được đề cập nhưng **chưa triển khai**:
[snapshot validator](../app/real_bundles.py):109 hiện chỉ nhận context `none`.
Chỉ mở khi có lỗi nối đoạn/xưng hô cụ thể; dùng glossary notes trước. Chưa cần
RAG, summary tự động, tự trích thuật ngữ, provider mới, crawler hoặc đổi stack.
Chọn một phần sách/dịch lại có chọn lọc chỉ mở khi có nhu cầu thực; hiện dùng
job toàn sách bất biến và resume phần thiếu, không sửa hợp đồng manifest cũ.

## Kiểm chứng và việc cần người dùng

Lượt này chạy kiểm tra offline trên core, real bundles/runner/Store và glossary:
**69 passed, 11 subtests, 1 deselected, 1 warning, 10,56s**. Bỏ chọn test web
glossary; không chạy full suite. Lệnh và kết quả cũng được ghi đầu
[HANDOFF](HANDOFF.md). Không dùng số test như bằng chứng chất lượng dịch,
full-book throughput hoặc độ bền Drive qua mất VM.

Việc local/viết kế hoạch không cần thao tác trực tiếp từ user. Trước phép thử
Colab tiếp theo, chủ tài khoản cần xử lý credential CLI đã lộ trong log theo
HANDOFF; xác thực/mount Drive và cấp runtime phù hợp khi thực hiện R3. Không
yêu cầu đưa token/code vào chat; không tự tạo GPU hoặc chạy dịch toàn sách.
Thử đọc trên EPUB reader và screen reader vẫn là kiểm chứng còn mở.

Verdict: giữ kiến trúc và review hiện có; triển khai reader R1 rồi nhớ chỗ đọc
R2, kiểm nhiều phiên R3 khi có điều kiện, cải thiện chất lượng dần ở R4.
Chưa kiểm: app/browser live, RAM/startup, chất lượng sách thật, full book và
resume qua VM mới. Một/vài phiên để xong toàn sách là mong muốn, chưa là cam kết.
