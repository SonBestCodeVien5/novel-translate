# Colab CLI trong repo

Dùng CLI từ [googlecolab/google-colab-cli](https://github.com/googlecolab/google-colab-cli).
Đã chuyển phiên bản 0.7.4 vào `.venv` chung với ứng dụng theo yêu cầu người dùng.
CLI được ghi trong extra `colab`; extra này cần Python 3.12 trở lên (ứng dụng
riêng vẫn hỗ trợ Python 3.11). Cài lại trong môi trường Python 3.12+:

```bash
UV_CACHE_DIR=/tmp/novel-translate-uv-cache uv pip install --python .venv/bin/python -e '.[test,colab]'
```

Wrapper luôn gọi `.venv/bin/colab` và giữ state phiên theo repo.
Chạy từ root repo:

```bash
./scripts/colab version
./scripts/colab --help
./scripts/colab restart-kernel --help
```

Nếu muốn gọi trực tiếp `colab`, bật môi trường bằng `source .venv/bin/activate`.
Dùng wrapper để session metadata luôn ở `data/colab-cli/`; gọi CLI trực tiếp
không có `--config` sẽ dùng đường dẫn state mặc định của CLI.

Wrapper đặt state phiên trong `data/colab-cli/` (Git ignore). Token đăng nhập
và log vẫn theo đường dẫn mặc định của CLI, `~/.config/colab-cli/`.
Không commit credential, token hoặc session metadata. CLI cần đăng nhập riêng
với Google; đăng nhập extension VS Code không tự cấp quyền cho CLI.

Đăng nhập lần đầu từ terminal VS Code:

```bash
./scripts/colab --auth oauth2 sessions
```

Bản 0.7.4 có sẵn cấu hình OAuth public: lệnh in URL để mở trên trình duyệt,
người dùng đăng nhập tài khoản đang chạy Colab, cấp quyền và nhập authorization
code vào chính terminal đang chờ. Không gửi code vào chat. Không cần cài gcloud
cho cách này. Người dùng đã đăng nhập; CLI đã đọc được runtime T4.

Sau khi cấu hình đăng nhập, `./scripts/colab sessions` liệt kê các runtime.
Phiên VS Code có thể hiện tên `[?]`: phiên đó chưa có metadata kernel trong
CLI. Không dùng tên `[?]` để restart hoặc đoán một kernel khác trên cùng VM.
Lệnh dưới đây chỉ dùng khi CLI đã quản lý đúng kernel cần reset:

```bash
./scripts/colab restart-kernel -s TEN_PHIEN
```

Restart làm mất biến/model trong kernel; checkpoint đã ghi trên Drive giữ
nguyên. Lệnh này không reset quota. `new` và `run` cấp runtime mới, `stop`
giải phóng runtime: không dùng các lệnh đó để reset kernel đang mở trong VS Code.
Đã gắn alias `qwen35-vscode` vào đúng kernel Qwen3.5 bằng metadata từ Jupyter
sessions đã xác minh, dùng `exec` để sửa/kiểm tra tokenizer và restart kernel
trên cùng runtime T4. Sau restart PID đổi từ 752 sang 7506, Drive còn nguyên và
GPU allocation về 0; không cấp runtime mới.

Để chạy luồng benchmark Qwen3.5 qua một lệnh trên runtime hiện có, dùng
[script tự động Qwen3.5](../archive/p0/docs/COLAB_AUTOMATION.md). Script kiểm kernel/package/Drive,
đồng bộ source, chạy và resume runner; không phải bấm từng cell trong VS Code.
