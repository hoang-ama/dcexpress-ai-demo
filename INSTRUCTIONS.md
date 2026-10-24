# DỰ ÁN: DC EXPRESS AI AGENT - PROJECT INSTRUCTIONS FOR ANTIGRAVITY IDE

> File này chứa toàn bộ bối cảnh nghiệp vụ, cấu trúc kỹ thuật, luồng dữ liệu, kịch bản mẫu và các bước tiếp theo để Antigravity IDE đọc hiểu và hỗ trợ lập trình trực tiếp cho dự án DC Express AI Agent.

---

## 1. TỔNG QUAN BỐI CẢNH DỰ ÁN (PROJECT OVERVIEW)

- **Tên dự án**: DC Express AI CSKH & Order Automation Agent.
- **Doanh nghiệp**: Công ty Cổ phần Vận tải Hàng hóa Đi Chung (DC Express / Dichung.vn).
- **Mục tiêu**: Tự động hóa luồng tiếp nhận nhu cầu, thu thập thông tin đơn hàng, tính giá cước, chốt đơn và bắn Lead lên hệ thống **DCHub Portal** (`portal.dichung.vn`) cũng như tương tác qua **Zalo OA** và **Hotline VoIP (19006022 / Asterisk)**.
- **Chiến lược hạ tầng**:
  - **70% tác vụ (Đặt đơn / Điền Form)**: Chạy hoàn toàn offline bằng LLM mã nguồn mở (**Qwen 2.5 7B / 1.5B**) trên server/VPS nội bộ qua **Ollama / Dify** để tối ưu chi phí (0 VNĐ Token).
  - **30% tác vụ (Hoàn, hủy, khiếu nại, tư vấn RAG)**: Chuyển tiếp sang Cloud AI (**Gemini 1.5 Flash**) có khống chế Token Quota & Context Caching.

---

## 2. CẤU TRÚC KỸ THUẬT & MÔI TRƯỜNG HIỆN TẠI (CURRENT TECH STACK)

- **Môi trường phát triển Local**: MacOS (Apple Silicon M3).
- **Local LLM Service**: Ollama running model `qwen2.5:7b` (Listening at `http://localhost:11434`).
- **Frontend / Prototyping Framework**: **Streamlit** (Python 3.9+).
- **File mã nguồn chính**: `app.py`.

---

## 3. LUỒNG NGHIỆP VỤ & KỊCH BẢN MẪU (SLOT FILLING & SAMPLE FORMAT)

### A. Cú pháp mở đầu (Initial Greeting Prompt):
```text
Bạn vui lòng cung cấp thông tin sau để chúng tôi lên báo giá:
- Người giao/ gửi hàng: tên/ điện thoại/ địa chỉ gửi
- Người nhận hàng: tên/ điện thoại/ địa chỉ nhận
- Thông tin hàng: tên hàng/ khối lượng/ kích thước/ số lượng/ ảnh chụp  
- Thời gian mong muốn giao/ nhận: ngày/ giờ  
- Ghi chú: ví dụ bốc xếp, ngõ hẹp...
```

### B. Quy tắc Slot Filling:
AI đóng vai trò Trợ lý CSKH DC Express, kiểm tra 5 nhóm thông tin:
1. Người gửi (Tên, SĐT, Địa chỉ gửi chi tiết).
2. Người nhận (Tên, SĐT, Địa chỉ nhận chi tiết).
3. Thông tin hàng (Tên hàng, Khối lượng/Kích thước/Số lượng).
4. Thời gian gửi/nhận mong muốn.
5. Ghi chú đặc biệt.

Nếu thiếu hoặc chưa rõ trường nào, AI sẽ nhắc nhở lịch sự để khách hàng làm rõ.

### C. Mẫu chuẩn khi đủ thông tin (Complete Summary Format):
```text
Thông tin sau khi khách hàng cung cấp đủ

Người gửi: Nhung/ ĐT: 0354327916
Đ/c gửi hàng: 144 Đ. Xuân Thủy, Cầu Giấy, Hà Nội, Việt Nam

Người nhận: anh Khánh/ ĐT: 0359920667
Đ/c nhận hàng: Đông Mai, Quảng Ninh, Việt Nam

Thông tin hàng: 1 thùng nước nuôi tôm/ Khối lượng: 10kg

Thời gian gửi: chiều ngày 22/10
Thời gian mong muốn nhận: trước 24/10

Ghi chú: Gửi trước 4h chiều, ngõ hẹp cách đường lớn 500m
```

### D. Cấu trúc JSON sạch mục tiêu (DCHub Portal API Payload):
```json
{
  "is_complete": true,
  "sender": {
    "name": "Nhung",
    "phone": "0354327916",
    "address": "144 Đ. Xuân Thủy, Cầu Giấy, Hà Nội, Việt Nam"
  },
  "receiver": {
    "name": "anh Khánh",
    "phone": "0359920667",
    "address": "Đông Mai, Quảng Ninh, Việt Nam"
  },
  "cargo": {
    "item_name": "thùng nước nuôi tôm",
    "weight_kg": 10.0,
    "description": "1 thùng nước nuôi tôm"
  },
  "schedule": {
    "pickup_time": "chiều ngày 22/10",
    "desired_delivery_time": "trước 24/10"
  },
  "notes": "Gửi trước 4h chiều, ngõ hẹp cách đường lớn 500m"
}
```

---

## 4. TRẠNG THÁI MÃ NGUỒN `app.py` ĐÃ HOÀN THÀNH

Ứng dụng `app.py` chia làm 2 cột chính (`st.columns([3, 2])`):
1. **Cột Chatbot UI**: Tương tác với người dùng theo cơ chế Stream từ Ollama `qwen2.5:7b`.
2. **Cột DCHub Portal API & Pricing Node**:
   - Sử dụng Regex bắt từ khóa `"Thông tin sau khi khách hàng cung cấp đủ"`.
   - Kích hoạt **Node JSON Extractor** (gửi prompt riêng cho Ollama để bóc tách văn bản thô ra JSON sạch).
   - **Tích hợp Module 1 (`pricing_engine.py`)**: Tự động nhận diện tuyến, quy đổi thể tích (/6000 & /5000), áp dụng biên lợi nhuận +30% và điền `pricing_estimate` vào JSON.
   - Giao diện trực quan cho phép so sánh cước phí (Đường bộ tiết kiệm vs Đường bay hỏa tốc) và chọn gói dịch vụ.
   - Mô phỏng Nút bấm Bắn API POST request tạo Lead trên DCHub Portal với kết quả HTTP 200 OK giả lập (kèm thông tin báo giá).

---

## 5. CÁC BƯỚC PHÁT TRIỂN TIẾP THEO (NEXT STEPS FOR ANTIGRAVITY IDE)

Khi làm việc trong Antigravity IDE, hãy triển khai tiếp các mô-đun theo thứ tự ưu tiên sau:

1. **Module 1: Tích hợp RAG Tra cứu Bảng giá DC Express (Pricing Calculation Engine)** - [✅ ĐÃ HOÀN THÀNH trong `pricing_engine.py` & `app.py`]
   - Nạp Bảng giá đường bộ, đường bay, xe tải, nội thành từ tài liệu công ty.
   - Xây dựng công thức tính cước:
     - Khối lượng quy đổi Đường hàng không: `Dài (cm) x Rộng (cm) x Cao (cm) / 6000`
     - Khối lượng quy đổi Đường bộ: `Dài (cm) x Rộng (cm) x Cao (cm) / 5000` hoặc `m3 x 250kg`
     - Công thức báo giá khách: `Giá báo KH = (Giá gốc / Giá thấp nhất đối tác) + 30%`.
   - Tự động điền cước phí tính toán vào payload JSON trước khi tạo đơn.

2. **Module 2: Middleware Kết nối Zalo OA OpenAPI & Chatwoot**
   - Xây dựng Webhook bằng FastAPI / Node.js.
   - Quản lý `chat_sessions` lưu vết `client_user_id` và `dify_conversation_id`.
   - Bật cơ chế Handover sang Chatwoot cho nhân viên trực nhấc máy khi gặp ca khó.

3. **Module 3: Kết nối Tổng đài VoIP Asterisk (SIP Trunk & Callbot)**
   - Cấu hình Asterisk PJSIP Trunk trỏ tới Voice AI Gateway (LiveKit / Vapi).
   - Sử dụng STT Whisper + Qwen 2.5 + Viettel TTS/FPT TTS.

4. **Module 4: Đóng gói Docker & Triển khai VPS**
   - Viết `docker-compose.yml` khởi chạy Dify, Chatwoot, Ollama, Nginx Reverse Proxy.

---

## 6. CÁC CÂU LỆNH CHUẨN ĐỂ VẬN HÀNH DỰ ÁN (PROJECT COMMANDS)

```bash
# 1. Tải và chạy mô hình Qwen 2.5 7B trên Ollama (Terminal local)
ollama run qwen2.5:7b

# 2. Khởi tạo môi trường ảo Python và Activate
python3 -m venv venv
source venv/bin/activate

# 3. Cài đặt các gói thư viện cần thiết
pip install streamlit requests

# 4. Khởi chạy ứng dụng Streamlit Demo
streamlit run app.py
```

---
*Ghi chú dành cho Antigravity IDE*: Hãy giữ nguyên các System Prompt và Định dạng JSON mẫu trong file này để đảm bảo dữ liệu đôn hàng đồng bộ tuyệt đối với hệ thống Backend DCHub Portal.
