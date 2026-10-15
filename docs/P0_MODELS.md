# Các ứng viên P0 EN → VI

## Quyết định provider tích hợp — 15/10/2026

User xác nhận đã chấm và chọn `Qwen/Qwen3.5-4B` làm provider tích hợp; đây là
model mới được thêm gần nhất. Chưa có báo cáo/số đo benchmark trong repo để ghi
nhận 25% time saving, 18/18 chunks, đủ hai model hoặc zero critical errors.
Không suy ra formal P0 phase/quality gate đã hoàn tất. `criteria.json` hiện còn
`measurements_status=not_run` và `decision=null`, chưa được cập nhật theo thông
tin user.

Mốc cấu hình repo cho tích hợp: revision
`851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`, `transformers==5.3.0`,
`accelerate==1.11.0`, `bitsandbytes==0.48.2`, NF4 double quant với compute fp16,
SDPA, batch 1, budget source/input/output/context 768/2048/2048/4096, greedy,
seed 0, `enable_thinking=False`. Đây là profile P0 đã có smoke để làm mốc kỹ
thuật; không đại diện số đo hay cấu hình do user vừa cung cấp. Không tự thay
model/config trong quá trình tích hợp.

Các ghi chú về benchmark preparation/smoke bên dưới là lịch sử theo thời điểm;
quyết định mới nhất là lựa chọn provider ở trên.

## Bổ sung Qwen3.5-4B — 15/10/2026

Cập nhật kiểm chứng: đã chạy thật một chunk trên T4 qua CLI, `technical_complete`,
830 input / 922 output tokens, EOS; session ghi đúng revision pin, load khoảng
34,29 giây. Đã xử lý `BatchEncoding` của Transformers 5.3 và config nested thiếu
commit hash bằng kiểm tra SHA snapshot đã resolve. Đây là smoke kỹ thuật,
chưa đo/chấm đủ năm chương hoặc có quyết định chất lượng. Luồng tự động ở
[COLAB_AUTOMATION.md](COLAB_AUTOMATION.md); các ghi chú chưa chạy bên dưới là
trạng thái lúc chuẩn bị notebook.

Theo yêu cầu người dùng, thêm [notebook riêng](../notebooks/p0_qwen35_benchmark.ipynb)
cho `Qwen/Qwen3.5-4B`, revision
`851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`. Dùng cùng corpus/glossary,
prompt, seed 0 và greedy để so với hai ứng viên ban đầu; tắt thinking bằng
`enable_thinking=False` trong chat template, ghi cấu hình vào snapshot.
Model này có kiến trúc vision-language; runner chỉ nạp phần ngôn ngữ bằng
`Qwen3_5ForCausalLM`, không xử lý hình ảnh.

Cấu hình nhắm Colab Free/T4: NF4 4-bit + double quantization, compute/load
float16, batch 1, attention SDPA, source target 768, input tối đa 2.048,
output reserve 2.048, context chạy 4.096 token. Không dùng BF16 hoặc cài
FlashAttention/FLA/causal-conv1d; đường PyTorch dự phòng có thể chậm.
Notebook mới pin `transformers==5.3.0`, `accelerate==1.11.0`,
`bitsandbytes==0.48.2`; không dùng pin Transformers 4.57.3 của hai bản cũ.

Trên runtime Qwen3.5 hiện có, smoke một chunk đã đạt `technical_complete`
(830 input / 922 output tokens, EOS; revision pin được xác minh). Lượt tự động
đã resume từ checkpoint và tại quan sát gần nhất hoàn tất 4/18 chunk, đang xử lý
chunk thứ năm. Đây là snapshot trạng thái, chưa phải kết quả full bền vững.
Notebook cũng có thể chạy bằng Run all độc lập; không chạy đồng thời với script
trên cùng kernel.

Chọn runtime GPU, chỉ nạp một model. Mặc định `LIMIT=1` thử một chunk
trên corpus full tại `MyDrive/p0/corpus.json`; đây chưa phải benchmark đủ
năm chương. Đặt `LIMIT=None` để tiếp tục toàn bộ chunk cùng snapshot;
checkpoint được kiểm tra trước khi resume, output nằm riêng dưới
`runs/Qwen3.5-4B-<snapshot>`. Không đọc bản dịch trước khi xong baseline.
Đã dùng runtime T4 hiện có; chưa đo/chấm đủ năm chương, VRAM, tốc độ tổng thể
hoặc chất lượng. Không bảo đảm Colab cấp T4/quota. Không tự tăng trần bốn phiên
GPU đã chốt hoặc tự khởi chạy phiên mới.

Căn cứ: [model/config chính thức tại revision cố định](https://huggingface.co/Qwen/Qwen3.5-4B/tree/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a),
[Transformers 5.3 Qwen3.5](https://huggingface.co/docs/transformers/v5.3.0/model_doc/qwen3_5),
[mã loader/model 5.3.0](https://github.com/huggingface/transformers/blob/v5.3.0/src/transformers/models/qwen3_5/modeling_qwen3_5.py).

## Hai ứng viên ban đầu

Đối chiếu metadata chính thức ngày 14/10/2026; **chưa chạy GPU hay chấm chất lượng**.
Hai repo public, không gated tại lần kiểm tra; Apache 2.0 cho model không cấp
quyền sử dụng truyện. Chưa chọn provider cho ứng dụng.

| | A | B |
| --- | --- | --- |
| Model | Qwen/Qwen3-4B-Instruct-2507 | Qwen/Qwen2.5-7B-Instruct |
| Revision cố định | `cdbee75f17c01a7cc42f958dc650907174af0554` | `a09a35458c702b33eeacc393d103063234e8bc28` |
| Tham số | 4,022,468,096 | khoảng 7.61 tỷ |
| Context trong config | 262,144 | 32,768; không bật YaRN |
| Template SHA-256 | `64f85b198065d0fba2a81f37e10ed68161ce2c19a754c7100e67e0ca2ee9c326` | `cd8e9439f0570856fd70470bf8889ebd8b5d1107207f67a5efb46e342330527f` |
| Căn cứ EN→VI | Card mô tả đa ngôn ngữ, chưa chứng minh chất lượng VI | Card liệt kê Vietnamese trong hơn 29 ngôn ngữ, chưa chứng minh chất lượng dịch novel |

A là bản non-thinking, không truyền `enable_thinking`. Cả hai dùng
`Qwen2Tokenizer`, BPE, EOS `<|im_end|>`, pad `<|endoftext|>`; tokenizer
`model_max_length` (A 1,010,000; B 131,072) không thay context thật trong config.
Runner dùng đúng template từ revision cố định, ghi lại template/hash; cùng prompt,
glossary, seed 0, greedy, context nguồn trước = none. Input tối đa 2,048 token
sau template; reserve 2,048 output, context chạy 4,096; source target 768 token,
batch 1. Chia chunk bằng tokenizer của từng model nên ranh giới có thể khác;
chấm cùng năm chương và đối chiếu offsets, không so tốc độ chỉ theo số chunk.

Riêng notebook Qwen2.5, hai lượt đã dừng ở chunk đầu với 2.048 output tokens
và token lặp; `repetition_penalty=1.1` ở lượt hai không giải quyết được lỗi.
Bản sửa tiếp theo bỏ phạt lặp này, dùng NF4 4-bit với compute float32 và các
phần không lượng tử float32. Runner lấy precision từ config, không ép fp16.
Snapshot/plan và thư mục kết quả đổi theo config; các ngân sách token giữ nguyên.
[Qwen troubleshooting](https://qwen.readthedocs.io/en/v2.0/inference/chat.html#troubleshooting)
cảnh báo float16 có thể gây mất ổn định số/lặp; đây là căn cứ thử precision,
chưa chứng minh nguyên nhân trên phiên T4. Lượt thử cấu hình float32 sau đó OOM
ngay khi nạp model, nên chưa có bằng chứng cấu hình này sinh ổn định hay chất
lượng tốt hơn; xem trạng thái mới trong [HANDOFF](HANDOFF.md). Không chạy thêm
lượt GPU khi chưa có quyết định riêng. Ghi khác biệt cấu hình khi so hai model.

Hai notebook đều dùng NF4 4-bit và double quantization. Qwen3 dùng compute
float16; notebook Qwen2.5 đặt compute float32 cho weights NF4 và các phần không
lượng tử, theo cấu hình riêng sau lỗi lặp đã ghi ở trên. Notebook pin `transformers==4.57.3`,
`accelerate==1.11.0`, `bitsandbytes==0.48.2`: **chưa kiểm thử trên Colab**.

| Bộ nhớ (GiB) | A | B |
| --- | --- | --- |
| Trọng số 4-bit tối thiểu lý thuyết | 1.87 | 3.54 |
| Trọng số fp16 lý thuyết | 7.49 | 14.18 |
| KV fp16 tại 4,096 token | 0.5625 | 0.21875 |
| Ngân sách thực dụng ước tính để thử | 4–7 | 6–10 |

Ước tính trọng số = tham số × 0.5 byte / 2³⁰; KV =
2 × layers × KV heads × head dimension × 2 bytes × tokens.
A: 36/8/128; B: 28/4/128. Chưa gồm đầy đủ embeddings không lượng tử,
scales, activations, CUDA và peak khi load; **không phải VRAM thực đo**.
T4 16 GB là cấu hình thử khả dĩ nếu được cấp, không phải cam kết.
[Colab FAQ](https://research.google.com/colaboratory/faq.html) nêu tài nguyên,
GPU và quota miễn phí không được bảo đảm; không tự chuyển sang gói trả phí.

Nguồn model A: [card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507),
[config pin](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/raw/cdbee75f17c01a7cc42f958dc650907174af0554/config.json),
[tokenizer pin](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/raw/cdbee75f17c01a7cc42f958dc650907174af0554/tokenizer_config.json),
[license pin](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/raw/cdbee75f17c01a7cc42f958dc650907174af0554/LICENSE).
Nguồn model B: [card](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct),
[config pin](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct/raw/a09a35458c702b33eeacc393d103063234e8bc28/config.json),
[tokenizer pin](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct/raw/a09a35458c702b33eeacc393d103063234e8bc28/tokenizer_config.json),
[license pin](https://huggingface.co/Qwen/Qwen2.5-7B-Instruct/raw/a09a35458c702b33eeacc393d103063234e8bc28/LICENSE).
Cả hai LICENSE SHA-256: `832dd9e00a68dd83b3c3fb9f5588dad7dcf337a0db50f7d9483f310cd292e92e`.
