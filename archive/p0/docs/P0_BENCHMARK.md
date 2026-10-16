# Chuẩn bị benchmark P0 (tài liệu lưu trữ)

Tài liệu này ghi lại quy trình cũ, không phải hướng dẫn chạy benchmark hiện hành.
User đã chọn Qwen3.5 làm provider tích hợp; metrics chưa được lưu trong repo.
Không cần notebook/script trong archive để dùng app. Các trạng thái và đường dẫn
bên dưới là ghi chép lịch sử tại thời điểm tương ứng.

**Trạng thái 15/10/2026: Qwen3.5 smoke kỹ thuật đạt; full run đang chạy/resume.
Benchmark hoàn tất/chất lượng và go/no-go chưa có.**

Cập nhật 15/10/2026: bổ sung [notebook Qwen3.5-4B](../notebooks/p0_qwen35_benchmark.ipynb)
bên cạnh hai notebook cũ, theo [cấu hình Colab Free](P0_MODELS.md).
Bản mới mặc định `LIMIT=1` thử một chunk trên corpus full; sau khi kiểm tra,
đặt `LIMIT=None` để resume các chunk còn lại. Chạy mỗi model trên runtime GPU
riêng. Qwen3.5 đã chạy thật qua CLI trên T4; một chunk hoàn tất kỹ thuật và lượt
full đã resume trên cùng runtime hiện có. Không mở thêm phiên hoặc tăng ngân sách.
Các ghi chép A/B dưới đây là thiết kế hai ứng viên ban đầu;
khi chấm thêm ứng viên C, giữ cùng năm chương, baseline và rubric, thêm dòng
review cho C và cân bằng thứ tự ba ứng viên. Không suy ra kết quả từ test offline.

Cập nhật 14/10/2026: đã nhận đủ `data/p0/text/ch01.txt`–`ch05.txt`.
Đã chuẩn bị corpus full và hai notebook chạy riêng từng model; nguồn TXT giữ
nguyên, URL ch03–ch05 và quyền nguồn chưa xác minh. Ch01–ch02 dùng Airn,
ch03–ch05 dùng Irene; chưa đối chiếu khác biệt bản nguồn. Những ghi chép thiếu
ba chương/smoke dưới đây là lịch sử chuẩn bị trước lần cập nhật này.
Hai notebook và corpus full đã lên Drive; corpus được đọc lại xác minh đúng bytes.
Cấu hình corpus full: `MyDrive/p0/corpus.json`; notebook Run all vẫn hỗ trợ,
script CLI là đường chạy hiện tại của Qwen3.5. Smoke `ch01-0000` đạt
`technical_complete` (830 input/922 output tokens, EOS). Lượt full đã resume
`1/18`; tại quan sát gần nhất hoàn tất 4/18 và đang xử lý `ch02-0001`.
Đây là trạng thái theo thời điểm, không đảm bảo runtime vẫn hoạt động. Xem [HANDOFF](../../../docs/HANDOFF.md)
để biết giới hạn kiểm chứng; không chạy notebook đồng thời trên cùng kernel.
Người dùng cho phép sinh bản máy trước, dịch tay sau; không đọc output trước
khi hoàn thành baseline. Notebook chỉ in trạng thái/counts, bản dịch lưu riêng. Có runner/notebook thử nghiệm độc lập;
ứng dụng P1 vẫn dùng provider giả. Không mở tích hợp provider hoặc crawler P4; EPUB import local được mở riêng
theo yêu cầu người dùng, xem [EPUB_IMPORT.md](../../../docs/EPUB_IMPORT.md).

Người dùng chọn EN → VI, ngân sách 0 đồng, Colab free, tự review; đã đồng ý:
không bỏ đoạn, mọi chunk hoàn tất, không còn lỗi sai ý trọng yếu sau review,
thời gian sinh + sửa giảm ít nhất 25% so với dịch thủ công cùng nguồn.
[criteria.json](../benchmarks/p0/criteria.json) ghi quyết định ngày 14/10/2026:
tiếng Việt tự nhiên, giữ giọng nhân vật và tên riêng; tối đa 2 lần thử/model,
tổng 4 phiên Colab miễn phí. Benchmark chưa chạy/chấm.
Hai ứng viên, revision, giấy phép và ước tính VRAM: [P0_MODELS.md](P0_MODELS.md).

## Nguồn và chuẩn bị offline (lịch sử smoke trước corpus full)

Hai TXT hiện có mang provenance [Webnovel](https://www.webnovel.com/vi/book/27050623305192205/72613479139302959),
theo thứ tự chương 1–5 có Prologue; giữ nguyên làm bộ mẫu hiện tại. Người dùng
đã chọn [FreeWebNovel](https://freewebnovel.com/novel/reformation-of-the-deadbeat-noble)
làm nguồn mới, nhưng Playwright gặp Cloudflare security verification nên chưa xác minh
mục lục, ch03–ch05 hoặc đối chiếu hai nguồn. Không suy ra chúng tương đương.
Nguồn cũ NovelFull chọn chapter 1–5 không Prologue; provenance được ghi riêng trong
[source_manifest.json](../benchmarks/p0/source_manifest.json), không trộn cách đánh số.

Đã có `data/p0/text/ch01.txt` (Prologue, 8.889 byte, 1.660 từ) và `ch02.txt`
(The Lazy Prince Picks Up a Sword (1), 8.826 byte, 1.592 từ). Đây là TXT chép tay
của người dùng, thân tiếng Anh dù heading tiếng Việt; giữ nguyên bytes/newline.
Manifest ghi hash TXT, counts và coverage quan sát ở hai chương; raw HTML/hash
là null vì không có bản HTML gốc của thao tác chép tay. Chương 3–5 chưa có;
tiêu đề và URL riêng chưa xác minh nên để null, không suy từ NovelFull.
Trang công khai được chọn trả HTTP 403 khi tải trực tiếp; Playwright ngày
14/10/2026 gặp Cloudflare security verification. Đã dừng, không vượt chặn;
TOC và ch03–ch05 chưa xác minh. Trạng thái/checkpoint ở
[`data/p0/source-check.json`](../../../data/p0/source-check.json).

`rights_status=unverified`: chưa có bằng chứng quyền dịch/phân phối của chủ quyền.
Cho phép tiếp tục chỉ là chuẩn bị riêng, không chứng minh nguồn licensed/cleared.
Không đăng toàn văn vào Git. Hai chương hiện có chỉ đủ smoke test; **chưa đủ
corpus benchmark chính thức năm chương**. Smoke output dùng `corpus-smoke.json`
và phải được đánh dấu riêng; không chấm hoặc suy ra go/no-go từ smoke.

Khi có đúng năm TXT UTF-8 được phép sử dụng, đặt riêng tại `data/p0/text/ch01.txt`
đến `ch05.txt`; giữ raw riêng trong `data/p0/raw/`. Người chuẩn bị kiểm tra từng
file đúng chapter, không menu/quảng cáo, ghi metadata/hash và căn cứ quyền vào
bản manifest riêng; không tự cắt/chuẩn hóa source. Trước khi chạy lệnh đủ năm
chương, cập nhật manifest: tiêu đề ch03–ch05 từ file thực, URL nếu biết và hash
TXT thực; các tiêu đề null hiện tại sẽ bị từ chối. Không sinh tiêu đề/nội dung giả.
Lệnh offline cho đủ năm chương (chưa chạy vì thiếu ch03–ch05):

```bash
python benchmarks/p0/prepare_corpus.py --manifest benchmarks/p0/source_manifest.json --output data/p0/corpus.json data/p0/text/ch01.txt data/p0/text/ch02.txt data/p0/text/ch03.txt data/p0/text/ch04.txt data/p0/text/ch05.txt
```

Script không truy cập mạng, giữ UTF-8/newline nguyên trạng, kiểm tra hash nếu
manifest có, từ chối rỗng/sai encoding/thứ tự và không ghi đè corpus đã có.
Giới hạn mỗi chapter 4 MiB UTF-8, toàn corpus JSON canonical 16 MiB.
Corpus chứa provenance/rights chưa xác minh và hash text. Bản raw HTML/hash là
metadata riêng, không được suy từ hash TXT. `data/` bị Git ignore; corpus,
plan/results chứa toàn văn nên cũng chỉ lưu riêng/Drive, không commit.

Hai chương đã đọc có dialogue/names/pronouns/description; coverage này chỉ áp dụng
cho phần đã có. Cần đọc thêm ba chương và ghi chapter dài nhất toàn bộ corpus. Chưa xác minh cả năm đạt độ dài đại diện; người dùng cần
đo/ghi token của nguyên chapter qua tokenizer/template/glossary thực và cộng
reserve output: phải vượt budget chạy 4,096 token để chứng minh ca dài.
Có >1 chunk ở target 768 chỉ chứng minh chunking, chưa chứng minh vượt context.
Không cần vượt context công bố 262K/32K của model. Runner tự in và lưu
`chapter_measurements` cho từng chương/model: `full_input_tokens`,
`output_reserve`, `context_tokens`, `exceeds_context`; không cần chạy đoạn đo riêng.
Phép đo chỉ in ID/count, không in toàn văn. Nếu cả năm không có ca vượt budget,
ghi thiếu coverage; không lấy chương thứ sáu hoặc nhân bản nguồn.

## Baseline và review

Copy [baseline.csv](../benchmarks/p0/baseline.csv), [review.csv](../benchmarks/p0/review.csv),
[errors.csv](../benchmarks/p0/errors.csv) vào `data/p0/review/` trước khi điền.
Năm dòng baseline và mười dòng A/B là phiếu trống, không phải kết quả; ô trống
CSV và null JSON là chưa đo, không phải 0. Giữ draft/final, đoạn lỗi và bản sửa
ở đường dẫn riêng; không đưa nội dung novel vào CSV được commit.
Nếu hai chương smoke sẽ dùng lại trong benchmark, không xem bản dịch smoke
trước khi hoàn thành baseline dịch tay của chính hai chương đó.

1. Người dùng dịch tay **đúng toàn bộ năm chương**, không hỗ trợ model, trước
   khi xem output; bấm giờ drafting + review, giữ draft/final riêng.
2. Randomize nhãn mù A/B và giữ khóa nhãn riêng; cân bằng thứ tự xem/sửa theo
   chương (A trước/B trước luân phiên, thứ tự ban đầu chọn ngẫu nhiên).
   Cùng reviewer, rubric, nguồn và glossary; không sửa prompt giữa hai ứng viên.
3. Ghi lỗi trước sửa và sau sửa theo source/chunk/span, correction và severity.
   Categories: omission/addition, meaning, name, pronoun, dialogue, style.
   Critical: đảo/sai ý quan trọng, mất đoạn, sai người nói/đối tượng làm đổi ý;
   major: lỗi cần sửa để đọc đúng; minor: diễn đạt/nhất quán nhỏ. Chấm văn phong
   1–5 theo thang người dùng chốt trước; không coi technical_complete là đạt chất lượng.
4. Giờ sửa tính cả đọc so nguồn, sửa tên/xưng hô/ý và review cuối; ghi riêng
   generation/load/wall time. `saving = 1 - (generation_minutes + editing_minutes)
   / baseline_total_minutes`. Không cộng load vào metric đã chốt, nhưng báo riêng
   end-to-end (load + sinh + sửa), download, GPU time và thời gian gián đoạn.
   Không tính saving khi thiếu baseline, thời gian hoặc chunk.
5. Chỉ đạt nếu mọi chương/all chunks đạt technical và review, không bỏ đoạn,
   zero critical sau review, tổng saving năm chương ≥25%, đạt style đã chốt.
   Ghi cả tổng và mỗi chương, không lấy trung bình tỷ lệ thay tổng thời gian.

Reviewer đã biết nguồn sau baseline và nhớ output đầu có thể làm lần sau nhanh
hơn: counterbalance giảm nhưng không loại learning effect; báo hạn chế này.

## Chạy thật bằng notebook người dùng mở

[Notebook P0](../notebooks/p0_benchmark.ipynb) tự chứa mã runner/validator;
không cần upload hoặc copy repo. Upload notebook lên Colab, chọn GPU miễn phí,
chạy kiểm tra GPU trước khi cài package, rồi chạy package pins và bootstrap
mã vào `/content/p0-code`. Notebook không chứa toàn văn novel hoặc SQLite.
Mount Drive bằng auth của người dùng, cùng tài khoản đã nhận corpus. Plugin
Drive đã upload và đọc lại xác minh `MyDrive/p0/corpus-smoke.json` ngày
14/10/2026: 19.102 byte, SHA-256
`42db593b9738a93129c11da9a75e93c6b1c697ea72183b8eab16844a38ae9957`.
Không cần upload lại corpus hiện có; chi tiết riêng nằm trong `data/p0/`.
Đường dẫn Colab mặc định là `/content/drive/MyDrive/p0/corpus-smoke.json`.

Đã tạo corpus smoke riêng từ đúng hai TXT, không sửa nguồn:

```bash
.venv/bin/python benchmarks/p0/prepare_corpus.py --smoke --manifest benchmarks/p0/source_manifest.json --output data/p0/corpus-smoke.json data/p0/text/ch01.txt data/p0/text/ch02.txt
```

Notebook mặc định `LIMIT = 1`, chỉ thử một chunk; output tự tạo tại
`/content/drive/MyDrive/p0/runs/<model-short>-<snapshotsha256>` từ snapshot thực.
Sau reconnect, cùng corpus/model/revision/config sẽ dùng lại output này;
đổi `LIMIT = None` khi muốn chạy nốt smoke. Kết quả vẫn mang nhãn smoke,
không được dùng làm benchmark chính thức. Khi đủ năm chương, tạo corpus chính
bằng lệnh phía trên và đổi `CORPUS` trong notebook; snapshot mới dùng output riêng.
Chạy A và B ở phiên tách biệt để không giữ hai model trong VRAM.
Package pins chưa kiểm thử Colab; nếu thiếu GPU, lỗi quyền/OOM thì ghi lại và dừng,
không mua tài nguyên hoặc retry vô hạn. Notebook người dùng lưu trước đó có GPUcheck `CUDA: True`, `GPU: Tesla T4`;
metadata riêng ghi đây là output đã lưu do main quan sát, không phải xác nhận
phiên đang sống hoặc model đã chạy. Cập nhật 15/10/2026: đã cài và đăng nhập
[Colab CLI](../../../docs/COLAB_CLI.md), gắn đúng kernel Qwen3.5 đang mở trong VS Code.
Luồng điều khiển qua CLI không cần bấm từng cell; xem HANDOFF để biết kết quả
kiểm chứng mới nhất, không suy ra GPU inference đạt chỉ từ việc kết nối CLI.

Khi sửa runner/validator được nhúng, tái sinh notebook bằng
`python3 benchmarks/p0/build_notebook.py` rồi chạy test offline liên quan.
Notebook nhúng ba file mã tĩnh (`runner.py`, `app/bundles.py`, `app/__init__.py`),
không cần repo trên Drive.

CLI local `python benchmarks/p0/runner.py --help` chỉ kiểm tra giao diện.
Luồng CLI Colab lịch sử mô tả tại [COLAB_AUTOMATION.md](COLAB_AUTOMATION.md);
notebook vẫn là lựa chọn Run all độc lập. Không chạy cả hai trên cùng kernel.

Thử một chunk, giữ Drive checkpoint, ngắt runtime rồi load lại/run đúng lệnh
với cùng snapshot (đổi `LIMIT = None` khi đã kiểm tra). Xác minh result hợp lệ được
bỏ qua và chunk dở chạy lại; đây là **kiểm tra còn phải làm**, không claim đã đạt.
Không đổi source/glossary/model/prompt trong output folder cũ; dùng run mới,
không xóa hoặc ghi đè machine/manual artifacts. Partial/checksum/config mismatch
phải dừng báo lỗi; failed/needs_review cần review và run mới có chủ đích.

Runner lưu `plan.json`, từng `results/*.json`, `sessions/*.json`: revision,
template/hash, source offsets/hash, token thực, timing, GPU/VRAM/software và
peak CUDA; result có session_id liên kết facts phiên. Attention `eager` được pin.
`session_seconds` chỉ là thời gian runner (từ tokenizer download), không gồm
pip/mount/idle; người dùng bấm giờ toàn phiên được cấp GPU riêng cho GPU time.
`load_seconds` gồm download + load; `download_seconds` null nếu
không tách đo được, cost null nếu chưa có số liệu. Drive FUSE không bảo đảm
POSIX durability: revalidate file/checksum sau reconnect, không coi sync là atomic.
Các file này **không phải bundle import P1**; chưa import vào app.

## Kết quả và quyết định

Tại thời điểm ghi mục này chưa có số liệu thật hay model được chọn. Báo cáo cuối phải đủ năm chương × hai
ứng viên, nguồn/config bất biến, lỗi trước/sau, baseline, coverage chương dài,
ngắt/resume, GPU/quota và chi phí thực. Chọn model chỉ khi ngưỡng chốt đạt;
không đạt thì ghi no-go/đổi ứng viên, không tự mở phase kế tiếp.
