# 📦 DC Express AI Agent - CSKH & Order Automation

[![DC Express AI Agent CI](https://github.com/hoang-ama/dcexpress-ai-demo/actions/workflows/ci.yml/badge.svg)](https://github.com/hoang-ama/dcexpress-ai-demo/actions/workflows/ci.yml)

Hệ thống AI Agent tự động hóa tiếp nhận nhu cầu đặt đơn theo **Kịch bản tư vấn tự nhiên 5 giai đoạn (Kỹ thuật "Rả rích / Luộc ếch" - Progressive Disclosure)** giúp khách không bị ngợp form, tích hợp RAG Pricing Engine (+30% Margin), Order Confirmation và trích xuất JSON sạch chuẩn API DCHub Portal (`portal.dichung.vn`).

---

## 🌟 Tính Năng Nổi Bật

1. **Kịch Bản Tư Vấn Tự Nhiên (Progressive Slot-Filling "Luộc ếch")**:
   - **Giai đoạn 1**: Thu thập nhẹ nhàng 3 thông tin critical để tính giá (Điểm gửi/nhận ➔ Hàng hóa ➔ Thời gian & Ghi chú). Không hỏi dồn dập tên/SĐT ngay từ đầu.
   - **Giai đoạn 2**: Báo giá minh bạch (Đường bộ tiết kiệm / Hỏa tốc đường bay) & Chốt đồng ý giá với khách.
   - **Giai đoạn 3**: Thu thập thông tin vận hành (Liên lạc 2 đầu ➔ Bên thanh toán ➔ Hình thức thanh toán).
   - **Giai đoạn 4**: Tiện ích gia tăng (Hỏi nhanh về xuất VAT & Bảo hiểm hàng hóa bổ sung).
   - **Giai đoạn 5**: Xuất Phiếu xác nhận đơn hàng (**Order Confirmation**), gửi nhà xe và tự động gửi thông tin tài xế cho khách ngay khi xếp tài.
2. **DC Express Pricing Calculation Engine (Module 1)**:
   - Tự động nhận diện phân vùng tuyến đường (Nội thành, Liên tỉnh cùng miền, Bắc - Nam).
   - Quy đổi khối lượng thể tích theo chuẩn logistics: Đường bay (`/6000`), Đường bộ (`/5000`).
   - Tự động áp dụng biên lợi nhuận +30% (`Giá báo KH = Giá gốc đối tác + 30%`).
   - So sánh đồng thời 2 dịch vụ: 🚚 **Đường bộ tiết kiệm** và ✈️ **Hỏa tốc đường bay**.
3. **Dual Engine Kiến Trúc Hybrid**:
   - **Local Mode (0đ Token)**: Chạy qua Ollama `qwen2.5:7b` On-premise.
   - **Cloud Mode**: Tự động Fallback sang Google Gemini khi triển khai Online trên Server/Cloud.
4. **DCHub Portal Integration & Driver Dispatch**:
   - Tự động bóc tách JSON Payload chuẩn hóa theo schema đơn hàng hoàn chỉnh.
   - Mô phỏng quy trình tạo Lead và Điều phối tài xế (Bắn SMS/Zalo thông tin tài xế cho khách).

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
