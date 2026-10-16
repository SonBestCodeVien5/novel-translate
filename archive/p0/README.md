# Lịch sử benchmark P0

Thư mục này lưu mã, notebook, test và hướng dẫn benchmark P0 cũ để tra cứu.
User đã chọn `Qwen/Qwen3.5-4B` làm provider tích hợp; không cần chạy lại các
artifact này để dùng app. Luồng app hiện hành nằm ở `docs/REAL_BATCH.md` và
`docs/INTEGRATION.md`.

Metrics benchmark chưa được lưu trong repo. `criteria.json` là artifact lịch sử
với trạng thái `not_run`; không coi archive là quality gate hay bằng chứng chất
lượng. Notebook/script P0 là các thử nghiệm độc lập, không phải khuyến nghị chạy
cho luồng app.

Các test lịch sử có thể chạy từ thư mục này:

```bash
cd archive/p0
PYTHONPATH=. ../../.venv/bin/python -m pytest -q tests/test_p0.py tests/test_p0_corpus.py tests/test_p0_progress.py tests/test_colab_pipeline.py
```

`app/` giữ đúng hai module đã nhúng trong notebook để test generator/runner lịch sử
độc lập với app hiện tại. Test Colab có thể skip nếu extra `colab` chưa cài. Lệnh
đã kiểm tra trong môi trường repo: 40 passed.
