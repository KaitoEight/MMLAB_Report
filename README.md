# Xác nhận Paper — người gửi hoặc admin

Trong bảng **Báo cáo**, mỗi dòng Paper có nút **Xác nhận** ở cột Thao tác. Bấm nút đó hoặc tiêu đề Paper để mở phần **Xác nhận thông tin Paper**:

- **Gửi email xác nhận**: tạo email cho đúng người forward từ email gốc, kèm form đã điền sẵn. Khi đã có thư gửi trước đó, nút đổi thành **Gửi lại email xác nhận**, cấp link mới và vô hiệu link cũ. Email đang chờ/đang truyền không được tạo trùng.
- **Xem email và link xác nhận**: xem người nhận, tiêu đề, nội dung, mở form công khai. Không cần đăng nhập để dùng form có token.
- **Admin xác nhận**: admin kiểm tra và xác nhận ngay, không cần chờ email của người gửi. Thông tin Paper phải đầy đủ/hợp lệ, có tác giả thuộc lab. Nếu chưa đạt, bấm Sửa báo cáo để bổ sung rồi xác nhận lại.

Hệ thống ghi rõ người xác nhận (admin/người gửi), thời gian và phiên bản báo cáo. Admin xác nhận sẽ hủy email yêu cầu xác nhận còn pending/retry. Thư đã gửi hoặc đang truyền không thu hồi được. Form cũ không thể ghi đè Paper đã được admin xác nhận.

Sau khi sửa một Paper đã xác nhận, bản mới trở về Chờ xác nhận; lịch sử xác nhận cũ vẫn được giữ. Xác nhận dữ liệu không tự đổi trạng thái bài báo thành Accepted và không xác minh Scopus/ranking bên ngoài.

Dữ liệu chỉ nhập JSON chưa xác minh được người forward: có thể admin xác nhận sau khi kiểm tra, nhưng gửi email cần đọc lại email gốc qua IMAP. Vào Thiết lập dữ liệu → Cập nhật ngay, đợi quét xong rồi mở lại Paper.

Để gửi email thật, đặt `MAIL_MODE=smtp` và chạy `run_local.py`. Chế độ preview vẫn tạo nội dung/link để xem, không gửi thật. Link localhost chỉ mở được trên máy host; dùng PUBLIC_BASE_URL HTTPS thực tế để người gửi truy cập từ máy khác.

**Cập nhật Windows:** dừng app → chép đè ZIP, giữ `.env`, `data/`, `secrets/` → chạy lại `run_local.py` → Ctrl+F5. Không cần nhập lại dữ liệu hoặc tạo lại tài khoản.

---

# Sửa cách tổng hợp báo cáo tháng — bản nối dòng

Bản này nối các dòng tiếp diễn trước khi gộp trùng, giữ nguyên hai công việc khác nhau dù có cùng dòng mở đầu. Chuẩn hóa cách ghi ngày và dấu đầu dòng; gộp cùng công việc/cùng người/cùng ngày, không gộp giữa hai người hoặc hai ngày.

- Không còn dòng riêng “tạp chí…”, “trong lĩnh vực…”, “track Creative” khi có ngữ cảnh tiếp diễn liền trước.
- Chia nội dung theo chủ đề; không đặt công việc hành chính dưới nhãn “Chi tiết công trình”.
- Ẩn các đề mục trống và dòng “Chưa có nội dung báo cáo” trong bản xuất có dữ liệu.
- Nội dung chưa rõ người gửi hoặc có dấu hiệu bị cắt chỉ kèm bản thảo luận, không đưa vào bản nộp trường. Không đoán phần còn thiếu hay tự sửa email.
- Không đổi kỳ theo ngày ghi trong nhiệm vụ: kỳ thống kê vẫn là ngày Gmail nhận thư.

Cập nhật: dừng app, chép đè ZIP, giữ `.env`, `data/`, `secrets/`, chạy lại `run_local.py`. Vào **Báo cáo tháng → chọn tháng tổng hợp 2026-08 → Tổng hợp lại → Lưu báo cáo** rồi tải Word cho tháng 09. Bản tùy chỉnh đã lưu không bị tự ghi đè. Nếu cần giữ chỉnh sửa riêng, lưu một bản Word trước khi tổng hợp lại.

Worker tự đọc lại các email báo cáo tháng cũ còn trong INBOX theo quy tắc mới. File JSON cũ vẫn được nối dòng khi tổng hợp, nhưng không thể khôi phục phần văn bản đã bị mất khỏi JSON. Muốn bổ sung nội dung đó phải đọc lại email gốc hoặc admin sửa báo cáo nguồn.

---

# MMLab — tổng hợp báo cáo hoạt động

Ứng dụng Python/FastAPI + React, chạy Windows bằng SQLite; có Docker Compose/PostgreSQL khi triển khai Ubuntu. Không tính điểm KPI. Chỉ admin đăng nhập; người nhận link xác nhận Paper mở đúng form mà không cần tài khoản.

## Cập nhật bản Windows đang chạy

1. Dừng app bằng Ctrl+C. Sao lưu `data/`, `.env`, `secrets/`.
2. Giải nén ZIP, chép đè các file trong `mmlab-selfhost` vào thư mục dự án cũ. Giữ nguyên ba mục đã sao lưu.
3. Mở PowerShell tại thư mục có `run_local.py`, cài thêm thư viện xuất Word:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

4. Trong `.env`, đặt:

```dotenv
MAIL_MODE=smtp
MONTHLY_REPORTS_ENABLED=true
```

5. Chạy lại:

```powershell
.\.venv\Scripts\python.exe run_local.py
```

Mở http://localhost:8080, nhấn Ctrl+F5 và đăng nhập. Vào **Thiết lập dữ liệu → Nhập dữ liệu có sẵn** để nhập `mmlab_export_normalized.json` được gửi riêng. Dữ liệu đã được admin sửa/xóa hoặc người gửi xác nhận không bị bản nhập đè lên.

Frontend đã build trong ZIP; không cần Node.js để chạy. Không có mật khẩu Gmail hoặc dữ liệu email thật trong ZIP.

## Cài mới trên Windows

Dùng Python 3.12 64-bit. Tại thư mục dự án:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe setup_local.py
.\.venv\Scripts\python.exe run_local.py
```

Setup hỏi tài khoản/mật khẩu admin và App Password Gmail. Muốn gửi thật, đặt `MAIL_MODE=smtp` trong `.env` rồi khởi động lại. `preview` chỉ giữ thư trong hàng đợi.

## Giao diện

- **Báo cáo:** bảng chi tiết, sửa/xóa, biểu đồ; lọc tháng/quý/năm/toàn bộ; xuất CSV.
- **Thành viên:** công trình tham gia và số bản khai của 12 thành viên.
- **Báo cáo tháng:** tổng hợp, sửa nội dung, tải hai bản Word.
- Mục thiết lập dữ liệu thu gọn ở cuối trang. Không còn các bảng trạng thái SMTP, thư cần kiểm tra và JSON kỹ thuật trên màn hình chính.

Phong cách tham khảo https://mmlab.uit.edu.vn/: nền trắng, chữ xanh đậm, thanh điều hướng ngang. Không thay đổi danh sách 12 thành viên theo nội dung website.

## Hai bản báo cáo cuối tháng

**09:00 giờ Việt Nam (Asia/Ho_Chi_Minh), thứ Hai cuối cùng mỗi tháng**, worker tự tổng hợp và gửi một email riêng cho từng người trong 12 địa chỉ chính thức. Mỗi email đính kèm:

1. **discussion.docx:** Đã tháng M (A.1/A.2) và Sẽ tháng M+1 (B.1/B.2), kiến nghị, người ký.
2. **school.docx:** chỉ kế hoạch Sẽ tháng M+1 (B.1/B.2), kiến nghị, người ký.

Ví dụ: lượt 28/09/2026 lúc 09:00 gồm kết quả tháng 09 và kế hoạch tháng 10. Bản trường được gửi cho 12 thành viên để hoàn thiện; ứng dụng chưa có địa chỉ người nhận của trường và không tự gửi ra ngoài danh sách này.

Kỳ lấy từ ngày Gmail nhận thư theo giờ Việt Nam, không lấy tháng trong Subject. Đây là bản chốt tại thời điểm gửi, không phải toàn bộ dữ liệu đến ngày cuối tháng: thư đến sau giờ chốt chưa có trong email đã gửi. Có thể mở lại kỳ đó và tổng hợp/tải Word mới sau này.

Máy phải bật, có mạng và `run_local.py` đang chạy. Sleep/tắt cửa sổ thì không gửi đúng giờ. Khi chạy lại, ứng dụng xử lý lượt cuối tháng gần nhất còn thiếu kể từ lúc cài tính năng, không gửi hàng loạt các tháng trước đó. Lịch được lưu trong database để tránh tạo lại cùng kỳ.

SMTP lỗi tạm thời có phản hồi rõ ràng được thử lại tối đa 5 lần. Nếu mất kết nối trong lúc truyền thư nên không biết Gmail đã nhận chưa, ứng dụng giữ trạng thái chưa rõ, không tự gửi lặp. Thông tin vận hành nằm trong log/database, không chiếm màn hình báo cáo. `MAIL_MODE=preview` không gửi thật; chuyển sang smtp sẽ gửi các thư còn pending. `MONTHLY_REPORTS_ENABLED=false` dừng tạo lượt tổng hợp mới; thư đã vào hàng đợi vẫn có thể gửi khi smtp bật.

### Phân nhóm và chỉnh sửa

Trong **Sửa báo cáo**, chọn KHCL / Thường xuyên và đột xuất / Chưa phân nhóm. Dữ liệu hiện tại không khai báo nhóm nên mặc định để riêng, không tự gán A.1/A.2 hoặc B.1/B.2. Admin có thể sửa nội dung từng phần ngay trong Báo cáo tháng. Nếu chưa khai báo KHCL/thường xuyên, Word trình bày dưới Phần A/B chung và chia theo nội dung (công bố, đề tài, đào tạo, seminar, giải thưởng, hướng dẫn sinh viên). Không tự gán nhiệm vụ vào KHCL. Các mục trống được ẩn trong bản có dữ liệu; mẫu trắng vẫn giữ các đề mục gốc.

Nếu chưa lưu bản tùy chỉnh, đến giờ gửi hệ thống tổng hợp từ dữ liệu hiện có. Nếu admin đã **Lưu báo cáo**, lượt gửi dùng nội dung đã lưu. Muốn cập nhật thêm email mới vào bản đã lưu, bấm **Tổng hợp lại → Lưu báo cáo**. Lưu không gửi email ngay và không gửi lại kỳ đã chốt. Hai cửa sổ sửa đồng thời được kiểm soát phiên bản, tránh ghi đè.

Mẫu Word trắng trong `templates/`. Tên KHCL “giai đoạn 2021-2025” và ghi chú kế hoạch 2023 được giữ theo mẫu cung cấp, chưa xác nhận là mẫu hiện hành. Tên KHCL/người ký sửa được trên dashboard; nội dung Word sửa được trước khi nộp. Các câu “Đã thực hiện seminar/Đã đạt giải” nằm trong phần kế hoạch của mẫu gốc được chuyển thành “Sẽ/Dự kiến” cho đúng hai phiên bản.

### Quy tắc tổng hợp

- Gộp Paper cùng tiêu đề và venue sau chuẩn hóa khoảng trắng/dấu; ví dụ MAPR2026 và MAPR 2026. Cùng bài có nhiều người forward chỉ đếm một công trình trong kỳ; hợp nhất thành viên tìm được.
- Chỉ cộng chỉ tiêu accepted/submitted khi có trạng thái khai báo tương ứng và có thành viên lab. Ranking hội nghị/tạp chí phải xác định được. Không xem “Decision available” là Accepted.
- Ghi nhận nguyên văn công việc Đã/Sẽ; chưa tự suy diễn số lượng, giai đoạn đề tài/NCS hoặc giải thưởng từ câu mơ hồ. Không tự bịa kế hoạch khi thiếu Sẽ.
- Thiếu Đã/Sẽ lưu null; block có nhưng trống lưu []. Không kiểm tra hợp lệ Subject, ngày/nội dung nhiệm vụ, Ranking/Accepted của báo cáo tháng. Người báo cáo vẫn được đối chiếu với danh sách lab.
- Thống kê là từ dữ liệu đã khai báo, không xác minh Scopus/ranking trên nguồn bên ngoài.

## Chuẩn hóa và kiểm tra file được cung cấp

File xuất chứa 530 thư đã xử lý, 123 thư có dấu hiệu forward, 66 báo cáo: 50 Paper, 11 báo cáo tháng, 4 đề tài, 1 NCS. Sau chuẩn hóa và bỏ lỗi schema cũ không áp dụng, 54 báo cáo đạt kiểm tra trường, 12 còn lỗi (ban đầu 45/21).

Lỗi còn lại: 11 bản có Ranking `Unranked` hoặc `-`; 1 lỗi Index `-` (trùng một bản có lỗi ranking); 1 báo cáo có mailbox người gửi `anhndt@uit.edu.vn` khác email chính thức `anhntd@uit.edu.vn`. Không tự sửa email này. Có 50 bản vẫn giữ trạng thái Chưa rõ; 3 bản được nâng thành Accepted từ Subject chứa thông báo chấp nhận rõ ràng. Các số valid không đồng nghĩa công trình duy nhất, đã được chấp nhận hoặc đã được người gửi xác nhận.

Role dùng bảng alias trước (`Co-authors`, `Co author`, `đồng tác giả` → `Co-author`). Chỉ khi alias không khớp mới xét cosine similarity trên character n-gram, ngưỡng 0.78 và chênh lệch ứng viên 0.15. Vai trò mơ hồ giữ nguyên để bổ sung. Không áp dụng cosine cho tên, email, Accepted hoặc ranking mơ hồ. Ranking có alias rõ (`C-unrank`, `A-ranked`); `Unranked` không biết hội nghị/tạp chí thì giữ lỗi.

Dữ liệu nhập không có toàn bộ email gốc. Không thể phục hồi nội dung thiếu hoặc xác thực người forward chỉ bằng file này. Nhập JSON không tự phản hồi từng email Paper cũ; IMAP phải đọc nguồn email để xác định đúng người nhận. Dữ liệu đã nhập được dùng làm nguồn cho báo cáo tháng theo lịch.

## Luồng Paper và quyền admin

Người dùng tự forward Paper đến lab. Worker đọc IMAP ở chế độ read-only, nhận diện và trích xuất, tạo email xác nhận với link form đã điền sẵn cho **From ở lớp ngoài cùng**. Không lấy người nhận phản hồi từ From bên trong thư gốc. Tự động bỏ qua các thư auto-reply/no-reply để tránh vòng lặp. Thư cũ trước mốc bật tự động không nhận hàng loạt thư phản hồi; có thể chọn Tạo email xác nhận trong chi tiết Paper.

Link công khai chỉ sửa một Paper, hạn 7 ngày, không cần đăng nhập/OTP. Form vẫn kiểm tra các trường Paper và yêu cầu người gửi đánh dấu đã kiểm tra. Admin có thể sửa/xóa tất cả báo cáo. Xóa là ẩn khỏi báo cáo và chặn tạo lại khi quét; email gốc Gmail vẫn giữ. Link cũ bị thu hồi, email chưa gửi bị hủy. Nếu xóa lỗi, giao diện hiện mã HTTP và nội dung server; gửi nguyên dòng lỗi cùng traceback để chẩn đoán.

Link `localhost` chỉ mở được trên máy host. Để thành viên dùng từ máy khác, cấu hình reverse proxy HTTPS và đặt `PUBLIC_BASE_URL`/`APP_ORIGIN` cùng địa chỉ thật, `COOKIE_SECURE=true`. ZIP không tự tạo tên miền hay public URL.

## Vận hành và Ubuntu

Sao lưu Windows khi app đã dừng: toàn bộ `data/`, `secrets/`, `.env`. Các bảng bản thảo/lịch gửi nằm cùng database nên cần giữ khi chuyển máy để tránh mất nội dung hoặc dấu đã gửi. Có thể chuyển nguyên SQLite và chạy Python trên Ubuntu bằng venv, giữ cấu hình/secrets/data và cài requirements tương tự.

Cài mới bằng Docker Compose:

```bash
python3 setup_local.py
docker compose up -d --build
```

Ứng dụng chỉ bind localhost; dùng reverse proxy cho truy cập ngoài máy. PostgreSQL không mở cổng public. Backup Docker: `python3 scripts/backup_docker.py`, đồng thời sao lưu `.env` và `secrets/`. Script `backend/migrate_sqlite.py` cũ chỉ chuyển báo cáo/snapshot, chưa chuyển toàn bộ xác nhận, bản thảo và lịch gửi; không dùng script đó như bản chuyển hệ thống đầy đủ.

Chỉ chạy một worker cho một hộp thư/database. Bản Windows dùng `run_local.py` để quản lý API và worker cùng nhau. Lịch gửi là chức năng của ứng dụng tự host, không phải lịch chạy trên ChatGPT.

## Kiểm thử

94 test backend kiểm tra parser, quyền admin, sửa/xóa, xác nhận, chuẩn hóa, Word, lịch thứ Hai cuối tháng, timezone, chống gửi trùng và SMTP giả lập hai đính kèm. Frontend được build; smoke test chạy HTTP thực với dữ liệu giả lập. Hai mẫu DOCX được render để kiểm tra bố cục. Không gửi Gmail thật trong quá trình phát triển.

```bash
cd backend
python -m pytest tests -q
```

Cài `backend/requirements-dev.txt` nếu muốn chạy test. Test giao diện xử lý lỗi: `node scripts/test_api_errors.cjs`. Smoke native: `python scripts/smoke_local.py`.
