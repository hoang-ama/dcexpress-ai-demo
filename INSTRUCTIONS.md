# DỰ ÁN: DC EXPRESS AI AGENT - PROJECT INSTRUCTIONS FOR ANTIGRAVITY IDE

> File này chứa toàn bộ bối cảnh nghiệp vụ, cấu trúc kỹ thuật, luồng dữ liệu, kịch bản mẫu và các bước tiếp theo để Antigravity IDE đọc hiểu và hỗ trợ lập trình trực tiếp cho dự án DC Express AI Agent.

---

## 1. TỔNG QUAN BỐI CẢNH DỰ ÁN (PROJECT OVERVIEW)

- **Tên dự án**: DC Express AI CSKH & Order Automation Agent.
- **Doanh nghiệp**: Công ty Cổ phần Vận tải Hàng hóa Đi Chung (DC Express / Dichung.vn).
- **Mục tiêu**: Tự động hóa luồng tiếp nhận nhu cầu, thu thập thông tin đơn hàng, tính giá cước, chốt đơn và bắn Lead lên hệ thống **DC Hub Portal** (`portal.dichung.vn`) cũng như tương tác qua **Zalo OA** và **Hotline VoIP (19006022 / Asterisk)**.
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

---

## 3. LUỒNG NGHIỆP VỤ & KỊCH BẢN TƯ VẤN TỰ NHIÊN

Nhằm giúp khách hàng không bị ngợp hay nản lòng khi thấy một form dài, AI Agent áp dụng nguyên tắc **Progressive Disclosure (Rả rích từng tí một)**:

```text
[BƯỚC 1: ĐIỂM GỬI & NHẬN] ➔ [BƯỚC 2: HÀNG HÓA] ➔ [BƯỚC 3: THỜI GIAN & GHI CHÚ]
                                   │
                                   ▼ (ĐỦ 3 NHÓM CRITICAL ĐỂ TÍNH GIÁ)
                   [BÁO GIÁ CƯỚC & KHÁCH ĐỒNG Ý GIÁ]
                                   │
       ┌───────────────────────────┴───────────────────────────┐
       ▼ (KHÁCH ĐỒNG Ý MỚI HỎI TIẾP)                          
[BƯỚC 4: LIÊN LẠC 2 ĐẦU] ➔ [BƯỚC 5: BÊN TRẢ CƯỚC] ➔ [BƯỚC 6: CÁCH THANH TOÁN]
                                   │
                                   ▼ (ĐỦ THÔNG TIN VẬN HÀNH ĐƠN)
               [HỎI THÊM OPTIONAL: VAT & BẢO HIỂM BỔ SUNG]
                                   │
                                   ▼
             [ORDER CONFIRMATION: GỬI NHÀ XE & KHÁCH HÀNG]
                                   │
                                   ▼
            [KHI XẾP TÀI: GỬI INFO TÀI XẾ CHO KHÁCH & NGƯỢC LẠI]
```

### A. Chi tiết 5 Giai đoạn tương tác:

1. **Giai đoạn 1: Thu thập 3 thông tin Critical để tính giá**:
   - **Bước 1**: Điểm gửi (lấy hàng) và Điểm nhận (trả hàng).
   - **Bước 2**: Thông tin hàng hóa (Loại hàng, cân nặng kg, kích thước nếu có, ảnh chụp).
   - **Bước 3**: Thời gian mong muốn gửi/nhận & Ghi chú vận chuyển (ngõ hẹp, bốc xếp...).
   *(Tuyệt đối không hỏi Tên/SĐT ở giai đoạn này để tránh tâm lý dè chừng của khách).*

2. **Giai đoạn 2: Báo giá & Xác nhận đồng ý giá**:
   - Đủ 3 thông tin trên ➔ Pricing Engine tính toán ngay cước phí (+30% Margin).
   - Đưa ra phương án rõ ràng (Đường bộ tiết kiệm / Hỏa tốc đường bay).
   - Hỏi khách hàng xác nhận đồng ý mức giá. **Chỉ khi khách đồng ý mới bước sang giai đoạn tiếp theo**.

3. **Giai đoạn 3: Thu thập thông tin Vận hành & Thanh toán (Đủ điều kiện vận hành)**:
   - **Bước 4**: Thông tin liên lạc (Họ tên, SĐT đầu gửi và đầu nhận).
   - **Bước 5**: Bên thanh toán cước (Đầu gửi hay Đầu nhận thanh toán).
   - **Bước 6**: Cách thức thanh toán (Trả trước chuyển khoản hay Trả sau tiền mặt/COD).
   *(Có đủ 3 thông tin này là ĐỦ ĐIỀU KIỆN VẬN HÀNH ĐƠN)*.

4. **Giai đoạn 4: Thông tin Tiện ích gia tăng (Optional - Không bắt buộc)**:
   - Có cần xuất hóa đơn thuế VAT hay không?
   - Có muốn mua dịch vụ bảo hiểm bổ sung (khai giá hàng hóa) hay không?

5. **Giai đoạn 5: Order Confirmation & Điều phối tài xế**:
   - Xuất **Phiếu xác nhận đơn hàng (Order Confirmation)** gửi cho Khách hàng và Nhà xe.
   - Khi nhà xe xếp tài: Bắn thông tin tài xế (Tên, SĐT, Biển số xe) cho khách hàng và gửi thông tin khách hàng cho tài xế.

---

### B. Kịch bản hội thoại mẫu thực tế (Multi-turn Conversation):

- **AI**: "Dạ DC Express xin chào quý khách ạ! Em có thể hỗ trợ mình gửi hàng từ khu vực nào đến khu vực nào ạ?"
- **Khách**: "Mình muốn gửi từ Cầu Giấy Hà Nội về Đông Mai, Quảng Ninh."
- **AI**: "Dạ tuyến Hà Nội đi Quảng Ninh bên em có xe chạy liên tục trong ngày ạ. Anh/Chị cho em hỏi mình gửi mặt hàng gì, khối lượng khoảng bao nhiêu kg hoặc kích thước thế nào ạ?"
- **Khách**: "1 thùng nước nuôi tôm, nặng tầm 10kg bạn nhé."
- **AI**: "Dạ vâng ạ. Anh/Chị dự kiến khi nào gửi hàng và muốn người nhận nhận trước ngày giờ nào ạ? Chỗ mình gửi và nhận có ngõ hẹp hay cần hỗ trợ bốc xếp gì không ạ?"
- **Khách**: "Gửi chiều nay 22/10 trước 4h chiều, nhận trước ngày 24/10 nhé. Chỗ gửi ngõ hơi hẹp cách đường lớn 500m."
- **AI**: "Dạ em đã nắm được thông tin hàng của mình. Với đơn 1 thùng nước nuôi tôm 10kg từ Cầu Giấy về Đông Mai, Quảng Ninh:
  🚚 Cước vận chuyển Gói Tiết kiệm đường bộ là: **118.000 đ** (Giao tận nơi 1-2 ngày).
  Anh/Chị xem qua thấy mức giá và thời gian này đã phù hợp để bên em hỗ trợ lên đơn chưa ạ?"
- **Khách**: "Ok giá hợp lý đấy em, lên đơn cho anh đi."
- **AI**: "Dạ em cảm ơn anh đã tin tưởng DC Express! Để bên em sắp xếp tài xế qua lấy hàng đúng hẹn, anh cho em xin thông tin:
  - Đầu gửi: Tên, SĐT và số nhà cụ thể tại Cầu Giấy.
  - Đầu nhận: Tên, SĐT và địa chỉ người nhận tại Đông Mai ạ."
- **Khách**: "Người gửi: Nhung, SĐT 0354327916, 144 Xuân Thủy, Cầu Giấy. Người nhận: anh Khánh, SĐT 0359920667, Đông Mai, Quảng Ninh."
- **AI**: "Dạ đơn này bên mình đầu gửi thanh toán hay anh Khánh nhận hàng thanh toán ạ? Mình muốn thanh toán trước qua chuyển khoản hay trả tiền mặt khi giao nhận ạ?"
- **Khách**: "Đầu gửi thanh toán tiền mặt lúc tài xế qua lấy nhé."
- **AI**: "Dạ vâng ạ. Em hỏi thêm một chút là bên mình có cần xuất hóa đơn thuế VAT hoặc mua bảo hiểm hàng hóa bổ sung không ạ?"
- **Khách**: "Không cần em nhé."
- **AI**: "[PHIẾU XÁC NHẬN ĐƠN HÀNG - DC EXPRESS ORDER CONFIRMATION]
  Mã đơn: DC-HNQN-20261025-01
  Tuyến: 144 Xuân Thủy, Cầu Giấy ➔ Đông Mai, Quảng Ninh
  Hàng hóa: 1 thùng nước nuôi tôm (10kg)
  Gói cước: Đường bộ tiết kiệm - Tổng cước: 118.000 đ
  Người gửi: Nhung (0354327916) - Lấy hàng: Chiều 22/10 trước 16h (Ngõ hẹp 500m)
  Người nhận: anh Khánh (0359920667) - Nhận trước 24/10
  Thanh toán: Đầu gửi trả tiền mặt khi lấy hàng
  VAT: Không | Bảo hiểm: Không
  Trạng thái: ĐÃ XÁC NHẬN ➔ ĐANG ĐIỀU PHỐI TÀI XẾ.
  (Thông tin tài xế sẽ được gửi qua SMS/Zalo ngay khi nhà xe xếp chuyến!)"

---

### C. Cấu trúc JSON sạch mục tiêu (DC Hub Portal API Payload):
```json
{
  "order_code": "DC-HNQN-20261025-01",
  "workflow_stage": "confirmed",
  "is_price_agreed": true,
  "route_info": {
    "sender_area": "Hà Nội",
    "receiver_area": "Quảng Ninh",
    "route_type": "lien_tinh_cung_mien"
  },
  "cargo": {
    "item_name": "thùng nước nuôi tôm",
    "weight_kg": 10.0,
    "dimensions_cm": "30x20x20",
    "description": "1 thùng nước nuôi tôm"
  },
  "schedule": {
    "pickup_time": "chiều ngày 22/10, trước 16:00",
    "desired_delivery_time": "trước 24/10"
  },
  "notes": "Gửi trước 4h chiều, ngõ hẹp cách đường lớn 500m",
  "pricing": {
    "service_type": "Đường bộ tiết kiệm (DC Road)",
    "base_cost_vnd": 91000,
    "customer_quote_vnd": 118000,
    "margin_percent": 30.0,
    "is_accepted_by_customer": true
  },
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
  "payment": {
    "payer": "sender",
    "payer_display": "Đầu gửi thanh toán",
    "payment_method": "postpaid_cash",
    "payment_method_display": "Tiền mặt khi lấy hàng",
    "is_paid": false
  },
  "optional_services": {
    "vat_invoice": false,
    "tax_code": null,
    "additional_insurance": false
  },
  "dispatch_and_driver": {
    "status": "driver_assigned",
    "driver_name": "Nguyễn Văn Tuấn",
    "driver_phone": "0988123456",
    "vehicle_plate": "29H-123.45",
    "customer_notified": true,
    "driver_notified": true
  }
}
```

---

## 4. TRẠNG THÁI MÃ NGUỒN `app.py` ĐÃ HOÀN THÀNH

Ứng dụng `app.py` chia làm 2 cột chính (`st.columns([3, 2])`):
1. **Cột Chatbot UI**: Tương tác với người dùng theo cơ chế Stream từ Ollama `qwen2.5:7b`.
2. **Cột DC Hub Portal API & Pricing Node**:
   - Sử dụng Regex bắt từ khóa `"Thông tin sau khi khách hàng cung cấp đủ"`.
   - Kích hoạt **Node JSON Extractor** (gửi prompt riêng cho Ollama để bóc tách văn bản thô ra JSON sạch).
   - **Tích hợp Module 1 (`pricing_engine.py`)**: Tự động nhận diện tuyến, quy đổi thể tích (/6000 & /5000), áp dụng biên lợi nhuận +30% và điền `pricing_estimate` vào JSON.
   - Giao diện trực quan cho phép so sánh cước phí (Đường bộ tiết kiệm vs Đường bay hỏa tốc) và chọn gói dịch vụ.
   - Mô phỏng Nút bấm Bắn API POST request tạo Lead trên DC Hub Portal với kết quả HTTP 200 OK giả lập (kèm thông tin báo giá).

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
*Ghi chú dành cho Antigravity IDE*: Hãy giữ nguyên các System Prompt và Định dạng JSON mẫu trong file này để đảm bảo dữ liệu đôn hàng đồng bộ tuyệt đối với hệ thống Backend DC Hub Portal.
