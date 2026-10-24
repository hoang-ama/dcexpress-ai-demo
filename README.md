# 📦 DC Express AI Agent - CSKH & Order Automation

[![DC Express AI Agent CI](https://github.com/hoang-ama/dcexpress-ai-demo/actions/workflows/ci.yml/badge.svg)](https://github.com/hoang-ama/dcexpress-ai-demo/actions/workflows/ci.yml)

Hệ thống AI Agent tự động hóa tiếp nhận nhu cầu đặt đơn, Slot-filling thu thập 5 nhóm thông tin vận chuyển, tra cứu bảng cước RAG Pricing Engine (+30% Margin) và trích xuất JSON sạch chuẩn API DCHub Portal (`portal.dichung.vn`).

---

## 🌟 Tính Năng Nổi Bật

1. **Slot Filling Thông Minh**:
   - Tự động tiếp nhận và kiểm tra đủ 5 nhóm thông tin: Người gửi, Người nhận, Chi tiết hàng hóa, Thời gian gửi/nhận, Ghi chú đặc biệt.
2. **DC Express Pricing Calculation Engine (Module 1)**:
   - Tự động nhận diện phân vùng tuyến đường (Nội thành, Liên tỉnh cùng miền, Bắc - Nam).
   - Quy đổi khối lượng thể tích theo chuẩn logistics: Đường bay (`/6000`), Đường bộ (`/5000`).
   - Tự động áp dụng biên lợi nhuận +30% (`Giá báo KH = Giá gốc đối tác + 30%`).
   - So sánh đồng thời 2 dịch vụ: 🚚 **Đường bộ tiết kiệm** và ✈️ **Hỏa tốc đường bay**.
3. **Dual Engine Kiến Trúc Hybrid**:
   - **Local Mode (0đ Token)**: Chạy qua Ollama `qwen2.5:7b` On-premise.
   - **Cloud Mode**: Tự động Fallback sang Google Gemini 1.5 Flash khi triển khai Online trên Server/Cloud.
4. **DCHub Portal Integration**:
   - Tự động bóc tách JSON Payload chuẩn hóa.
   - Sẵn sàng kích hoạt API Tạo Lead tự động lên Portal Đi Chung.

---

## 🚀 Khởi Chạy Local (MacOS / Linux / Windows)

```bash
# 1. Clone repository
git clone https://github.com/hoang-ama/dcexpress-ai-demo.git
cd dcexpress-ai-demo

# 2. Khởi tạo và kích hoạt virtual environment
python3 -m venv venv
source venv/bin/activate   # Trên Windows: venv\Scripts\activate

# 3. Cài đặt thư viện
pip install -r requirements.txt

# 4. (Tùy chọn) Chạy Ollama nếu có
ollama run qwen2.5:7b

# 5. Khởi chạy Streamlit UI
streamlit run app.py
```

---

## ☁️ Triển Khai Online Miễn Phí (Streamlit Community Cloud)

1. Truy cập [share.streamlit.io](https://share.streamlit.io/) và đăng nhập bằng GitHub.
2. Bấm **"New app"** và chọn repository `hoang-ama/dcexpress-ai-demo`.
3. Nhập Main file path: `app.py`.
4. (Tùy chọn) Trong mục **Advanced settings -> Secrets**, thêm:
   ```toml
   GEMINI_API_KEY = "your_gemini_api_key_here"
   ```
5. Bấm **Deploy**! Bạn sẽ có ngay link web chia sẻ cho đối tác và khách hàng test 24/7.
