# Phiếu chuẩn bị benchmark P0

Trạng thái: **chưa chạy**. P1 dùng provider giả để kiểm tra dữ liệu; không phải
bằng chứng về chất lượng dịch, tốc độ model hoặc chi phí GPU/API.

## Chốt trước khi chạy

| Thông tin | Giá trị cần người dùng xác nhận |
| --- | --- |
| Ngôn ngữ | EN → VI, xác nhận ngày 14/10/2026 |
| Nguồn 5 chương | Chưa có; chỉ dùng nội dung có quyền sử dụng |
| Ứng viên A / revision | Chưa chọn |
| Ứng viên B / revision | Chưa chọn |
| Văn phong và người review | Chưa chốt |
| Trần chi phí và số lần thử | 0 đồng, Colab miễn phí theo phiên; số lần thử chưa chốt |
| Thiết bị/GPU, VRAM, tokenizer/template | Ghi từ phiên chạy thực |

Ngưỡng đề xuất cần chốt trước khi chấm: không bỏ đoạn, mọi chunk hoàn tất,
không còn lỗi sai ý trọng yếu sau review; tổng thời gian dịch và sửa giảm ít
nhất 25% so với baseline trên cùng mẫu. Chất lượng văn phong và trần chi phí
do người dùng chốt. Không coi ô trống là số 0.

## Kết quả thực đo

Mẫu cần bao gồm đối thoại, tên riêng, xưng hô, miêu tả và một chương dài.
Ghi config tái chạy: model/tokenizer revision, template, tham số sinh,
lượng tử hóa, chunk/context budget và phần cứng. Token chưa đo ghi `null`.

| Chương / ứng viên | Revision / cấu hình | Token vào / ra | Load / dịch (s) | Sửa tay (phút) | Baseline (phút) | Chi phí / GPU time | Lỗi / đạt ngưỡng |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 / A | | | | | | | |
| 1 / B | | | | | | | |
| 2 / A | | | | | | | |
| 2 / B | | | | | | | |
| 3 / A | | | | | | | |
| 3 / B | | | | | | | |
| 4 / A | | | | | | | |
| 4 / B | | | | | | | |
| 5 / A | | | | | | | |
| 5 / B | | | | | | | |

## Quyết định sau chấm

Chưa có quyết định go/no-go. Điền lỗi đại diện và bản sửa bằng đoạn nhỏ được
phép chia sẻ; giữ nguồn đầy đủ ngoài Git. Chỉ chọn provider thật khi có bằng
chứng đạt ngưỡng đã chốt trong [ROADMAP.md](ROADMAP.md).
