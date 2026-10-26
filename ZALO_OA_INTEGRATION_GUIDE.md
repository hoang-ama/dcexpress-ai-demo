# 📘 HƯỚNG DẪN KẾT NỐI ZALO OFFICIAL ACCOUNT (OA) & CHATWOOT LIVE AGENT

Tài liệu này hướng dẫn chi tiết dành cho Đội ngũ Kỹ thuật & Quản trị viên Đi Chung cách tích hợp **Zalo OA thật** với **DC Express AI Middleware (`zalo_middleware.py`)** và **Chatwoot Live Agent**.

---

## 1. TỔNG QUAN LUỒNG KẾT NỐI

```
[Khách hàng Zalo] 
       │ (1. Nhắn tin)
       ▼
[Zalo OpenAPI Gateway] 
       │ (2. Webhook POST /webhook)
       ▼
[DC Express Zalo Middleware (FastAPI)] ◄──► [Local Ollama / Gemini 3.8 Flash]
       │                                ◄──► [Pricing Engine (+30% Margin)]
       ├─────────────────────────────────► (Khi chốt đơn) [DCHub Portal API]
       ▼ (Khi khách yêu cầu gặp người / Khiếu nại)
[Chatwoot Live Agent Dashboard] ──(Tư vấn viên trả lời)──► [Gửi ngược về Zalo Khách]
```

---

## 2. CÁC BƯỚC CẤU HÌNH TRÊN ZALO DEVELOPERS (`developers.zalo.me`)

### Bước 2.1: Tạo Ứng Dụng (App) Trên Zalo for Developers
1. Truy cập [https://developers.zalo.me/](https://developers.zalo.me/) và đăng nhập tài khoản Zalo quản trị viên của Đi Chung.
2. Bấm **"Thêm ứng dụng mới"** ➔ Đặt tên: `DC Express AI Assistant`.
3. Trong mục **Cài đặt cơ bản**, ghi lại 2 thông số bảo mật:
   - **App ID** (ví dụ: `1234567890123456789`)
   - **Secret Key** (ví dụ: `abcdef1234567890abcdef`)

### Bước 2.2: Liên Kết Ứng Dụng Với Zalo Official Account (OA)
1. Trong menu bên trái, chọn **Official Account** ➔ **Quản lý Official Account**.
2. Bấm **"Liên kết Official Account"** và chọn OA chính thức của **Đi Chung Express**.
3. Cấp các quyền (Scope) bắt buộc:
   - `oa.message`: Cho phép đọc và gửi tin nhắn CSKH.
   - `oa.profile`: Xem thông tin cơ bản khách hàng.

### Bước 2.3: Cấu Hình Webhook URL
1. Chọn **Webhooks** trong menu Zalo App.
2. Nhập URL máy chủ công khai của bạn:
   ```
   https://api.dcexpress.vn/webhook
   # (Hoặc link ngrok khi test local: https://xxxx.ngrok-free.app/webhook)
   ```
3. Zalo sẽ tự động gửi một request `GET /webhook?hub.challenge=...` để kiểm tra.
   - Middleware `zalo_middleware.py` đã cài đặt sẵn cơ chế phản hồi `challenge` tự động, Webhook sẽ được verify **thành công ngay tức thì**.
4. Bật các sự kiện theo dõi:
   - `user_send_text`: Khi khách gửi tin nhắn văn bản.
   - `user_send_image`: Khi khách gửi ảnh kiện hàng.

---

## 3. LẤY MÃ OAUTH & KHỞI TẠO TOKEN TỰ ĐỘNG

Cơ chế của Zalo yêu cầu sinh mã **Authorization Code** 1 lần đầu tiên qua trình duyệt:

### Bước 3.1: Truy Cập Link Cấp Quyền OAuth
Mở trình duyệt và truy cập URL sau (thay `YOUR_APP_ID` bằng App ID của bạn):
```text
https://oauth.zaloapp.com/v4/oa/permission?app_id=YOUR_APP_ID&redirect_uri=https://api.dcexpress.vn/oauth/callback
```
- Đăng nhập và chọn Zalo OA của Đi Chung ➔ Bấm **Cho phép**.
- Trình duyệt sẽ chuyển hướng về `redirect_uri` kèm tham số `code=...`. Copy chuỗi mã `code` này (có hiệu lực trong 10 phút).

### Bước 3.2: Nạp Code Vào Middleware Để Sinh Tokens
Gọi API hoặc dùng trực tiếp giao diện Swagger UI (`http://localhost:8000/docs`):

```bash
curl -X POST "http://localhost:8000/oauth/exchange-code" \
     -H "Content-Type: application/json" \
     -d '{"code": "PASTE_MA_CODE_OAUTH_O_DAY"}'
```

🎉 **Xong!** Middleware sẽ tự động:
1. Lưu `access_token` và `refresh_token` vào file `.zalo_tokens.json`.
2. Tự động kích hoạt cơ chế **Auto-Renew trước 1 giờ** mỗi khi token sắp hết hạn (không bao giờ bị gián đoạn hoạt động).

---

## 4. TÍCH HỢP CHATWOOT LIVE AGENT (HUMAN-IN-THE-LOOP)

Khi khách hàng gõ các từ khóa: *"gặp nhân viên"*, *"khiếu nại"*, *"gọi lại cho tôi"*, bot sẽ tự động chuyển giao cho nhân viên trực chat:

1. Đăng ký tài khoản trên [app.chatwoot.com](https://app.chatwoot.com/) (hoặc Chatwoot On-premise).
2. Tạo một **API Access Token**: Vào **Profile Settings** ➔ Copy **Access Token**.
3. Cấu hình biến môi trường trong file `.env`:
   ```bash
   CHATWOOT_BASE_URL=https://app.chatwoot.com
   CHATWOOT_API_KEY=your_chatwoot_access_token
   CHATWOOT_ACCOUNT_ID=1
   CHATWOOT_INBOX_ID=1
   ```
4. Cấu hình **Webhook trên Chatwoot**:
   - Vào **Settings** ➔ **Integrations** ➔ **Webhooks** ➔ **Add new webhook**.
   - Nhập URL: `https://api.dcexpress.vn/chatwoot/webhook`.
   - Chọn sự kiện: `message_created`.
   - Khi nhân viên CSKH trả lời trên Chatwoot, tin nhắn sẽ tự động gửi thẳng về Zalo cho khách hàng!

---

## 5. TRIỂN KHAI PRODUCTION QUA DOCKER COMPOSE

Trên máy chủ VPS (Ubuntu/Debian), chỉ cần chạy:

```bash
# 1. Clone repository
git clone https://github.com/hoang-ama/dcexpress-ai-demo.git
cd dcexpress-ai-demo

# 2. Tạo thư mục dữ liệu bảo mật
mkdir -p data

# 3. Chạy toàn bộ hệ thống bằng Docker Compose
docker compose up -d --build

# 4. Kiểm tra trạng thái
docker compose ps
docker compose logs -f zalo-middleware
```

Kiểm tra sức khỏe hệ thống:
```bash
curl http://localhost:8000/health
```
Kết quả trả về:
```json
{
  "status": "healthy",
  "ollama_local_up": true,
  "zalo_token_valid": true,
  "chatwoot_configured": true,
  "active_sessions_count": 0
}
```
