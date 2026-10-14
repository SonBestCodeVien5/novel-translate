# Bàn giao phiên — 14/10/2026 (Asia/Bangkok)

Đọc sau WORKFLOW; đây là trạng thái vận hành, không thay PLAN/ROADMAP.
Chỉ tiếp tục **P0**, không mở P1/P2 hoặc crawler P4. P1 local fake đã có bằng
chứng trong P1.md; chưa chạy model thật, chưa có benchmark hay go/no-go.

## Đã chốt và còn mở

- EN → VI, ngân sách 0 đồng, Colab free theo phiên tương tác; người dùng tự review.
- Hai ứng viên: Qwen3-4B-Instruct-2507 và Qwen2.5-7B-Instruct; revision,
  package pins và cấu hình ở [P0_MODELS.md](P0_MODELS.md), không tự đổi snapshot.
- Benchmark chính thức: 5 chương × 2 model, không bỏ đoạn, mọi chunk hoàn tất,
  zero critical sau review, tổng thời gian sinh + sửa giảm ≥25% so baseline.
- Văn phong chi tiết và trần 2 lần thử/model, 4 phiên free vẫn là **đề xuất**,
  chưa được duyệt; chốt trước khi chạy/chấm chính thức.
- Baseline dịch tay cùng toàn bộ chương phải xong trước khi xem output model,
  kể cả hai chương smoke sẽ dùng lại; smoke không chứng minh chất lượng/go-no-go.

## Dữ liệu và bằng chứng hiện có

Nguồn người dùng chọn: [Webnovel](https://www.webnovel.com/vi/book/27050623305192205/72613479139302959),
5 chương đầu **có Prologue**; thay lựa chọn NovelFull cũ không có Prologue.
Giữ `data/p0/text/ch01.txt` (Prologue), `ch02.txt` (Lazy Prince (1)) nguyên bytes;
thân tiếng Anh, heading tiếng Việt. Chưa có ch03–ch05, title/URL riêng chưa xác
minh; quyền nguồn vẫn unverified. HTTP 403 đã được ghi, chưa có bằng chứng fetch
bằng Playwright; không suy ra đã crawl thành công hoặc vượt chặn truy cập.
Raw/source, machine output và sửa tay giữ riêng; không commit toàn văn hoặc data.

`data/p0/corpus-smoke.json` là corpus v2 hai chương, chỉ đủ smoke. Plugin Drive
đã upload và đọc lại xác minh đúng bytes ngày 14/10/2026 tại cùng tài khoản:
`MyDrive/p0/corpus-smoke.json`, 19.102 byte, SHA-256
`42db593b9738a93129c11da9a75e93c6b1c697ea72183b8eab16844a38ae9957`.
Metadata/link riêng ở `data/p0/drive-upload.json`; không nhờ upload lại file này.
Notebook người dùng lưu có `CUDA: True`, `GPU: Tesla T4`: output đã quan sát,
không chứng minh runtime đang sống, model đã load hay chất lượng dịch.

## Bước tiếp theo

1. Dùng [notebook P0](../notebooks/p0_benchmark.ipynb) hiện tại trên Colab GPU,
   cùng tài khoản Google; người dùng bấm Run all và xác nhận auth mount Drive.
   Chưa có công cụ kết nối để agent chạy kernel Colab của người dùng.
2. Mặc định `CORPUS=/content/drive/MyDrive/p0/corpus-smoke.json`, `LIMIT=1`.
   Notebook tự bootstrap mã vào `/content/p0-code`, không cần repo trên Drive.
   Chưa xem output nếu baseline các chương dùng lại chưa hoàn tất.
3. Output: `/content/drive/MyDrive/p0/runs/<model-short>-<snapshotsha256>`.
   Kiểm tra một chunk, reconnect cùng snapshot, rồi `LIMIT=None` để chạy nốt
   smoke khi phù hợp; ngắt/resume và GPU inference **chưa được kiểm thử thật**.
   Lỗi quyền/OOM/checksum/config thì dừng ghi bằng chứng, không retry vô hạn.
4. Hoàn thiện đúng ch03–ch05, metadata/quyền nguồn, coverage chương dài và các
   quyết định còn mở trước corpus chính thức; xem [P0_BENCHMARK.md](P0_BENCHMARK.md).

## Giữ phiên sau gọn

Giữ model main đang chọn; triển khai giao worker `gpt-6.1-sol`, reasoning `low`,
tối đa hai worker, mỗi file một owner, không lồng worker/heartbeat/poll.
Tiếng Việt ngắn, ponytail full: thay đổi nhỏ nhưng đủ, tái dùng sẵn có, không
thêm dependency/abstraction thừa, không hỏi lại việc đảo ngược đã được cho phép.
Dùng tool Drive có sẵn cho phần được giao trước khi nhờ người dùng làm tay.
Kết thúc báo điều đã làm, kiểm tra thực chạy, phần chưa kiểm và rủi ro.

Notebook nhúng ba file mã tĩnh; sau sửa runner/validator phải tái sinh bằng
`python3 benchmarks/p0/build_notebook.py` và chạy test offline liên quan.
Test offline không chứng minh CUDA, package pins, quyền nguồn hoặc chất lượng.
`timeout 60s .venv/bin/python -m pytest -q`: exit 0, 36 passed, 11 subtests passed,
1 warning (Starlette/httpx deprecated), 3.21s ngoài sandbox; lần trong sandbox timeout 40s.
Crawler được bảo vệ sau này phải dùng Playwright, cookies, retry giới hạn và
checkpoint bền vững để resume; chưa mở việc P4 trong phiên này.

Prompt mở phiên mới:
> Đọc AGENTS.md, docs/WORKFLOW.md, docs/HANDOFF.md rồi tiếp tục P0 từ trạng thái đã ghi; không mở P1/P2.
