# Luồng Paper: nhận thư → phản hồi → bổ sung → xác nhận

## Hành vi đã triển khai

1. Worker kiểm tra Gmail theo chu kỳ đang cấu hình (mặc định 60 giây sau mỗi lượt).
2. Với Paper được forward mới: trích xuất Title, All authors, Venue, Role, Index, Ranking.
3. Nếu thư chỉ là email acceptance/submission không có template, nhận diện Paper từ dấu hiệu rõ ràng, lấy tiêu đề nằm trong `titled "..."` khi có. Không đoán tác giả/ranking/index; để trống cho người gửi điền. Các trường hợp không nhận diện được vẫn nằm trong phần cần kiểm tra.
4. Tạo hồ sơ `pending` và đúng một email phản hồi cho mỗi outer Message-ID + người forward. Nếu thiếu Message-ID thì dùng UID nguồn.
5. Email ghi rõ **đã nhận**, các thông tin lấy được, `[CẦN BỔ SUNG]` và lỗi từng trường, kèm link form riêng.
6. Người gửi mở link không cần tài khoản admin. Form điền sẵn các trường lấy được, đánh dấu ô thiếu, cho sửa cả thông tin đã điền.
7. Bấm **Xác nhận & gửi**: server kiểm tra lại trường Paper. Nếu thiếu/sai, chỉ rõ lỗi. Nếu đầy đủ, lưu vào đúng bản ghi cũ, mapping lại thành viên và đổi trạng thái thành `confirmed`.
8. Quét Gmail lần sau giữ nguyên nội dung đã được người dùng xác nhận.

Đây là xác nhận **thông tin do người gửi khai báo**, không xác nhận thực tế bài đã xuất bản hoặc được Scopus/ISI lập chỉ mục. Báo cáo chưa có tác giả thuộc lab vẫn được lưu kèm cảnh báo, không tự gán người ngoài vào 12 thành viên.

## Thử ngay trên Windows, chưa gửi email thật

1. Dừng ứng dụng và chép đè `backend`, `frontend`, `compose.yaml` từ gói mới; giữ `.env`, `secrets`, `data`.
2. Trong `.env`, thêm:

```dotenv
MAIL_MODE=preview
PUBLIC_BASE_URL=http://localhost:8080
```

3. Chạy lại:

```powershell
.\.venv\Scripts\python.exe run_local.py
```

4. Sau khi ứng dụng khởi động, dùng email cá nhân forward một Paper đến `mmlab@uit.edu.vn`.
5. Dashboard → **Nguồn Gmail → Paper chờ người gửi xác nhận**.
6. Xem trước nguyên văn email và bấm **Mở form đã điền sẵn**. Bổ sung rồi submit; báo cáo đổi thành Đã xác nhận.

Thư đến trước thời điểm kích hoạt tính năng không tự được phản hồi, tránh gửi hàng loạt cho 524 thư lịch sử. Mốc này lưu trong database ngay lần khởi động bản có tính năng xác nhận. Để thử, hãy forward một thư mới sau khi khởi động; không cần sửa mốc.

Nhập JSON thủ công không tạo email phản hồi. Các Paper mới đi qua worker mới kích hoạt luồng này.

## Bật gửi Gmail thật

App Password đã lưu trong `secrets/gmail_password.txt` được dùng cho cả IMAP và SMTP của cùng `mmlab@uit.edu.vn`. Không đưa password vào source hoặc frontend.

```dotenv
MAIL_MODE=smtp
PUBLIC_BASE_URL=https://reports.ten-mien-cua-lab.vn
APP_ORIGIN=https://reports.ten-mien-cua-lab.vn
COOKIE_SECURE=true
```

Đây là URL minh họa; thay bằng tên miền/tunnel HTTPS thực sự trỏ tới backend đang chạy. Với người dùng khác máy, **localhost không sử dụng được**. Chạy qua Internet cần reverse proxy/tunnel HTTPS đến `127.0.0.1:8080`; cấu hình APP_ORIGIN và PUBLIC_BASE_URL đúng địa chỉ đang mở. Không cần chuyển Ubuntu để demo qua HTTPS, nhưng máy Windows và ứng dụng phải luôn bật.

Nếu chỉ gửi test cho chính mình và mở form trên máy đang chạy app, có thể giữ localhost và COOKIE_SECURE=false.

Dừng rồi chạy lại `run_local.py`; Docker dùng `docker compose up -d --build --force-recreate api worker`.

**Khi đổi sang smtp, các email đang pending từ chế độ preview cũng được gửi.** Kiểm tra danh sách xem trước trước khi chuyển chế độ.

Gmail SMTP dùng `smtp.gmail.com:465` với TLS xác thực chứng chỉ. Tài liệu chính thức:
https://developers.google.com/workspace/gmail/imap/imap-smtp

Chưa gửi thư thật từ môi trường tạo gói. Cần thử một email forward trên máy anh để xác nhận quyền SMTP của hộp thư.

## Người nhận, link và gửi lại

- Người nhận là đúng một địa chỉ ở **From của email forward bên ngoài**. Không dùng From/To/Cc của email gốc được trích dẫn, không reply-all và không suy ra người nhận từ tên tác giả. Không dùng Reply-To khác địa chỉ để tránh gửi lệch người forward.
- Không trả lời địa chỉ no-reply, mailer-daemon, hộp thư lab, thư danh sách/bulk hoặc auto-reply. Đây là định tuyến theo header đã nhận qua IMAP, không phải bằng chứng chống giả mạo danh tính tuyệt đối.
- Link riêng chứa token ngẫu nhiên, có hạn 7 ngày. Truy cập link chỉ đọc dữ liệu; chỉ POST có xác nhận rõ ràng mới lưu. Link chỉ có quyền với một Paper, không có quyền dashboard admin.
- Token đặt trong URL fragment, gửi đến API bằng Authorization header; không có email hoặc token trong URL API. Không chia sẻ link của người khác.
- Người gửi có thể submit lại cùng yêu cầu an toàn; sau khi đã xác nhận, form không sửa thêm. Chưa có luồng sửa lại Paper đã xác nhận trong bản này.
- Quản trị có thể bấm **Cấp link mới / gửi lại** khi còn pending. Link cũ hết hiệu lực, email mới vào hàng đợi. Trong chế độ smtp, thao tác này sẽ gửi lại thật.
- Email lỗi trước khi gửi có thể retry với thời gian chờ tăng dần, tối đa 5 lần. Nếu timeout sau khi đã bắt đầu gửi hoặc worker dừng giữa chừng, trạng thái là `unknown`; kiểm tra Sent trước khi chủ động gửi lại để tránh thư trùng.
- `sent` nghĩa là SMTP đã chấp nhận email, không chứng minh người nhận đã đọc hay nhận vào Inbox.
- Email nhận được ở chế độ MAIL_MODE=preview được giữ trong database để xem trước, không ghi file EML chứa link ra thư mục public.

## Trạng thái cần phân biệt

| Nội dung | Trạng thái |
|---|---|
| Đã nhận thư | Có hồ sơ Paper và email phản hồi pending/sent |
| Dữ liệu còn thiếu/sai | Form hiển thị lỗi và ô cần bổ sung |
| Người gửi chưa xác nhận | confirmationStatus=pending |
| Người gửi đã kiểm tra và submit thành công | confirmationStatus=confirmed |
| Email chưa xác định có gửi thành công không | mailStatus=unknown, quản trị kiểm tra |

Snapshot valid/invalid ở phần nguồn vẫn phản ánh kết quả trích xuất email ban đầu. Bảng báo cáo hiển thị dữ liệu hiện hành sau người dùng sửa và xác nhận.
