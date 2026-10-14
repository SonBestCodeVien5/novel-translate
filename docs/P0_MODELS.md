# Hai ứng viên P0 EN → VI

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

Riêng notebook Qwen2.5, sau lần chạy đầu dừng ở chunk đầu với 2.048 output
tokens và đuôi token lặp, thử `repetition_penalty=1.1`. Giá trị được ghi vào
config/snapshot/plan, tạo thư mục kết quả mới; các ngân sách token giữ nguyên.
Đây là điều chỉnh thử nghiệm chưa chạy lại GPU, cần ghi khác biệt cấu hình
khi so hai model. Checkpoint chưa hoàn tất cũ vẫn được giữ để đối chiếu.

NF4 4-bit, double quantization, compute fp16. Notebook pin `transformers==4.57.3`,
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
