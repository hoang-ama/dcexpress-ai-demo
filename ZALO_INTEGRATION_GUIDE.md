# ZALO OA WEBHOOK AND DCHUB PORTAL INTEGRATION GUIDE

Tài liệu này hướng dẫn chi tiết cách cấu hình Webhook Middleware kết nối giữa Zalo Official Account, AI Agent Engine và DCHub Portal Backend API.

---

## 1. TỔNG QUAN KIẾN TRÚC KẾT NỐI WEBHOOK

1. **Zalo OpenAPI**: Khách hàng chat trên Zalo OA -> Zalo OpenAPI phát sự kiện HTTP POST `user_send_text` tới URL Webhook của VPS.
2. **Nginx Reverse Proxy**: Nhận HTTPS trên cổng 443 và proxy_pass về Webhook Middleware (Cổng 8000).
3. **FastAPI Middleware**: 
   - Nhận sự kiện, lập tức phản hồi HTTP 200 OK (< 3 giây).
   - Đẩy tác vụ xử lý AI sang Background Worker.
   - Gửi query sang Dify / Ollama API (`http://localhost:80/v1/chat-messages`).
   - Nhận câu trả lời từ AI Agent -> Gửi phản hồi tin nhắn văn bản lại cho Zalo User.
   - Khi đơn hàng hoàn tất, trích xuất JSON và gửi POST Request sang DCHub Portal API để tự động tạo Lead.

---

## 2. CHÍNH SÁCH VẬN HÀNH & TỰ ĐỘNG CẤP LẠI TOKEN

- **RefreshToken Auto-renew**: Zalo OA Access Token có thời hạn sử dụng. Cần chạy Cronjob tự động đổi Refresh Token lấy Access Token mới mỗi 23 giờ.
- **Async Execution**: Mọi cuộc gọi API bên ngoài phải xử lý bất đồng bộ (Async / Background Task) để đảm bảo Webhook không bị gián đoạn.
