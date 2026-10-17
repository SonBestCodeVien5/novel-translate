# Chạy batch v2 trên Colab hiện có

`scripts/run_colab.py` tiếp tục job Qwen3.5 đã tạo local, chạy trên một alias
Colab đã đăng ký và nhập checkpoint từ Drive về SQLite local. Lệnh chỉ dùng
runtime đang có; không tạo VM hay tự dừng kernel/giải phóng runtime. OAuth dùng
phiên CLI hiện có; credential hết hạn được refresh trong bộ nhớ.
Colab phải là T4/GPU, kernel phải rảnh, và alias đã đăng ký phải khớp chính xác một `kernel_id` đang tồn tại. `session_id` có thể vắng mặt khi alias được tạo cho kernel có sẵn; khi có thì phải khớp session chính xác. Lệnh không đoán alias hoặc tạo kernel.

Trước tiên kiểm tra job mà không gọi OAuth hoặc mạng:

```bash
.venv/bin/python scripts/run_colab.py --data-dir data --job-id JOB_UUID \
  --session ALIAS --dry-run
```

Chạy tối đa một chunk mới để smoke, rồi tiếp tục các chunk còn thiếu:

```bash
.venv/bin/python scripts/run_colab.py --data-dir data --job-id JOB_UUID \
  --session ALIAS --limit 1
.venv/bin/python scripts/run_colab.py --data-dir data --job-id JOB_UUID \
  --session ALIAS
```

`--limit` đếm chunk mới sinh, không đếm checkpoint hợp lệ đã có. Mỗi chunk mới chạy trong một lượt riêng và được tải, validate, rồi import ngay trước chunk tiếp theo; model vẫn ở cùng kernel và được tái sử dụng. Lượt giới hạn trả trạng thái partial và không ghi lỗi giả cho các chunk còn thiếu. `--timeout`
mặc định 1800 giây và phải là số hữu hạn dương. Nếu execution timeout, kernel có
thể vẫn bận; lệnh chỉ ngắt kết nối websocket, thử thu result của chunk đó đã ghi bền vững, rồi dừng. Hãy đợi kernel idle trước khi chạy lệnh tiếp theo.

Lệnh chỉ chuyển manifest bất biến và bốn module runner cần thiết. SQLite, raw
source, token và nội dung result không được gửi qua log. Drive phải được mount
sẵn tại `/content/drive/MyDrive`; lệnh không mount Drive hoặc cài package. Pins
phải đúng `transformers==5.3.0`, `accelerate==1.11.0` và
`bitsandbytes==0.48.2`. Nếu thiếu, cài trong notebook hiện có rồi restart kernel:

```python
%pip install transformers==5.3.0 accelerate==1.11.0 bitsandbytes==0.48.2
```

Notebook `notebooks/translate.ipynb` dùng cùng `app.real_runner`, có `LIMIT=None`
để mặc định tiếp tục toàn bộ chunk còn thiếu. Notebook giữ thao tác mount Drive
cho người dùng và báo rõ nếu GPU hoặc pins không đúng.

Trên Drive, manifest nằm ở `MyDrive/novel-batch/<job_uuid>/manifest.json`, kết
quả hoàn tất nằm tại `MyDrive/novel-batch/<job_uuid>/results/<chunk_uuid>.json`.
CLI đọc danh sách thư mục results một lần rồi chỉ tải các file UUID dự kiến
có trong danh sách; thư mục 404 hoặc file chưa có được tính là pending. Lỗi đọc
hoặc danh sách không hợp lệ vẫn dừng bước chạy, không bị coi là checkpoint
trống. Mỗi result đã tải tiếp tục được validate đầy đủ trước import.
Runner và lệnh local từ chối manifest/checkpoint lệch; trước khi import, local
chỉ đọc tên result UUID dự kiến, giới hạn kích thước và validate lại provenance,
hash cùng job. Import trùng là no-op; result xung đột không ghi đè revision/sửa
tay. Sau execution lỗi hoặc timeout, các checkpoint hợp lệ vẫn được nhập riêng.
Nếu result đã có trong SQLite local nhưng chưa có trên Drive, CLI kiểm tra manifest
Drive và result local trước khi chép vào đúng tên UUID còn thiếu; file Drive có sẵn
được so sánh, không bị ghi đè khi xung đột. Các job khác glossary/context nhưng cùng
model, revision, lượng tử hóa và cấu hình attention vẫn tái sử dụng weights đang nạp;
tokenizer input IDs vẫn được tính và kiểm tra theo từng snapshot.

Chỉ dùng `--restart-kernel` khi muốn reset chính kernel alias đang idle. Lệnh xác
minh lại assignment, hardware, session và kernel sau restart. Mã runner đã đổi
trong kernel đang chạy cũng yêu cầu restart rõ ràng; module đã load không bị
reload và model không được nạp lần thứ hai.

Live smoke ngày 16/10/2026 đạt trên fixture tự tạo 2 chương/2 chunk với T4 và
pins nêu trên: `--limit 1` chạy/import result đầu; kernel restart cùng VM rồi
resume chunk hai, checkpoint Drive đầu đọc lại byte-identical, duplicate no-op và
manual edits được giữ. Nút UI trên job hoàn tất thu hai duplicate. Đây chưa chứng
minh mất VM/new VM, full 390 chương, hiệu năng/chất lượng hay native EPUB reader.
Offline tests dùng transport giả lập và không thay thế các kiểm chứng đó. Xem
[HANDOFF](HANDOFF.md) để biết cập nhật vận hành mới nhất.

Nếu mount qua CLI báo HTTP 400 sau consent, kiểm tra tài khoản Google đang hoạt
động trong trình duyệt có trùng tài khoản CLI hay không. Một lỗi tương tự và
cách chọn lại đúng tài khoản được ghi ở [issue #103 của Colab CLI](https://github.com/googlecolab/google-colab-cli/issues/103).
Đây là hướng chẩn đoán, không chứng minh nguyên nhân của mọi lỗi 400. Chỉ chủ
tài khoản xác nhận consent; không gửi token/code vào chat. Không bật
`--logtostderr` trong phiên agent: bản CLI hiện tại log cả HTTP authorization
header. Script v2 tắt logging SDK và chỉ in summary đã lọc.


Trang review của mỗi real job cũng có thể chạy/resume CLI local. Trang chỉ liệt kê alias T4 GPU đã đăng ký, mặc định chạy một chunk mới; để trống giới hạn nếu muốn chạy hết phần còn thiếu. Trạng thái tiến trình local được làm mới thủ công và hiển thị riêng với số checkpoint đã nhập SQLite. Web app không tạo, dừng hoặc giải phóng kernel. Cài `.[colab]` và đăng ký alias trước; script local giữ một khóa theo kernel để ngăn hai tiến trình cùng sử dụng.
