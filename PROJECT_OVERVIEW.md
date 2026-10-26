# DC EXPRESS AI AGENT - DỰ ÁN TỰ ĐỘNG HÓA CSKH & TẠO ĐƠN AUTOMATION

## 1. TỔNG QUAN DỰ ÁN & BỐI CẢNH NGHIỆP VỤ
- **Doanh nghiệp**: DC Express (Đi Chung Express - `dichung.vn` / `dichungexpress.com`).
- **Mục tiêu**: Tự động hóa luồng CSKH, tiếp nhận thông tin, tính cước RAG, chốt đơn và đẩy Lead tự động vào hệ thống **DCHub Portal** (`portal.dichung.vn`).
- **Kênh tiếp nhận chính**: 
  * Hotline VoIP: `19006022` / `0901778008` (Quản lý qua Asterisk / Caresoft).
  * Zalo OA: Official Account của DC Express.
  * Website Widget: `dichung.vn` / `dichungexpress.com`.

---

## 2. QUY TRÌNH TƯ VẤN KHÁCH HÀNG TỰ NHIÊN 5 GIAI ĐOẠN (CHIẾN THUẬT "RẢ RÍCH / LUỘC ẾCH")
Thay vì yêu cầu khách hàng điền một danh sách dài các trường thông tin (gây cảm giác ngợp form), AI Agent áp dụng nghệ thuật giao tiếp rả rích theo 5 giai đoạn:

```text
[GIAI ĐOẠN 1: CRITICAL TÍNH GIÁ] ──> [GIAI ĐOẠN 2: BÁO GIÁ & CHỐT GIÁ] ──> [GIAI ĐOẠN 3: VẬN HÀNH & THANH TOÁN]
(Điểm gửi/nhận, Hàng hóa, Thời gian)     (Khách đồng ý giá mới hỏi tiếp)       (Liên lạc 2 đầu, Bên trả, Cách trả)
                                                                                           │
                                                                                           ▼
[GIAI ĐOẠN 5: ORDER CONFIRMATION & XẾP TÀI] <── [GIAI ĐOẠN 4: TIỆN ÍCH GIA TĂNG (OPTIONAL)]
(Gửi nhà xe & KH; Bắn thông tin tài xế)          (Xuất hóa đơn VAT, Bảo hiểm bổ sung)
```

1. **Giai đoạn 1 (Critical để tính giá)**:
   - *Bước 1*: Điểm gửi và Điểm nhận.
   - *Bước 2*: Thông tin hàng hóa (Loại hàng, cân nặng kg, kích thước, ảnh chụp nếu có).
   - *Bước 3*: Thời gian mong muốn gửi/nhận & Ghi chú vận chuyển (ngõ hẹp, bốc xếp...).
2. **Giai đoạn 2 (Báo giá & Xác nhận đồng ý)**:
   - Pricing Engine tính cước (+30% Margin). Báo giá trực tiếp gói Tiết kiệm / Hỏa tốc.
   - Chờ khách hàng đồng ý phương án giá mới xin thông tin tiếp.
3. **Giai đoạn 3 (Thu thập thông tin Vận hành & Thanh toán)**:
   - *Bước 4*: Thông tin liên lạc (Họ tên, SĐT đầu gửi và nhận).
   - *Bước 5*: Bên thanh toán (Đầu nhận hay Đầu gửi).
   - *Bước 6*: Hình thức thanh toán (Trả trước chuyển khoản hay Trả sau tiền mặt/COD).
   *(Đủ 3 thông tin 4, 5, 6 là đủ điều kiện vận hành đơn hàng)*.
4. **Giai đoạn 4 (Tiện ích gia tăng - Optional)**:
   - Hỏi nhanh về nhu cầu xuất hóa đơn thuế VAT và Bảo hiểm hàng hóa bổ sung.
5. **Giai đoạn 5 (Order Confirmation & Xếp tài xế)**:
   - Xuất **Order Confirmation** cho nhà xe và khách hàng.
   - Khi nhà xe xếp tài: Bắn thông tin tài xế cho khách và gửi thông tin khách cho tài xế.

---

## 3. KIẾN TRÚC HYBRID 3 LỚP (OPTIMIZED FOR BUDGET & PERFORMANCE)

```text
[Khách hàng từ Hotline 19006022 / Zalo OA / Website]
                        │
                        ▼
┌──────────────────────────────────────────────────────────┐
│ LỚP 1: VPS NỘI BỘ (Ubuntu + Docker + Ollama + Dify)       │
│ • Model LLM Mã nguồn mở: Qwen 2.5 (1.5B / 7B)            │
│ • Core Router: Phân loại ý định, đón tiếp, Slot Filling  │
│ • Chi phí Token: 0 VNĐ (Chạy 100% On-premise)            │
└───────────────────────┬──────────────────────────────────┘
                        │
       ┌────────────────┴────────────────┐
       ▼ (70% Đặt đơn chuẩn hóa)         ▼ (30% Ca khó/Khiếu nại)
┌──────────────────────────────┐  ┌──────────────────────────────┐
│ LỚP 2: MIDDLEWARE API        │  │ LỚP 3: CLOUD AI PLATFORMS    │
│ • Zalo OA Webhook (FastAPI)  │  │ • Gemini Flash / Claude /    │
│ • API DCHub Portal (Tạo lead)│  │   OpenAI / Grok qua API Key  │
│ • Asterisk PJSIP (Callbot)   │  │ • Bật Context Caching & Quota│
└──────────────┬───────────────┘  └──────────────┬───────────────┘
               │                                 │
               └────────────────┬────────────────┘
                                │
                                ▼
         ┌──────────────────────────────────────────────┐
         │ LỚP PHỐI HỢP CON NGƯỜI (HUMAN-IN-THE-LOOP)   │
         │ • Chatwoot / CRM Nội bộ                      │
         │ • Chuyển máy cho Tổng đài viên (Zoiper)      │
         └──────────────────────────────────────────────┘
```

### Nguyên tắc Phân luồng 70/30 & Kiểm soát Ngân sách:
- **70% Tác vụ lặp đi lặp lại (Hỏi đường, xin thông tin, slot filling)**: Xử lý 100% bằng **Qwen 2.5** cài trên VPS nội bộ (Ollama / vLLM). Chi phí token = **0 VNĐ**.
- **30% Ca khó (Khiếu nại trễ chuyến, mất hàng, tính bảng giá RAG phức tạp)**: Chuyển sang **Gemini 1.5 Flash / Claude 3.5 Sonnet / OpenAI**.
- **Cơ chế khống chế ngân sách Cloud**:
  * **Context Caching**: Bật Caching cho file Bảng giá & Quy trình khiếu nại (giảm 75% phí token đầu vào).
  * **Max Token Limit**: Cấu hình giới hạn tối đa 1.500 tokens/session.
  * **Handover Trigger**: Tự động chuyển cho Tổng đài viên nếu khách nhập sai form > 3 lần hoặc có cảm xúc giận dữ.

---

## 4. CẤU TRÚC MÃ NGUỒN CỦA DỰ ÁN (`dcexpress-ai-demo`)
- `app.py`: Streamlit App demo giao diện Chat & RAG Pricing & DCHub API Node.
- `zalo_middleware.py`: FastAPI Webhook Middleware kết nối Zalo OA & Dify/Ollama.
- `PROJECT_OVERVIEW.md`: Tài liệu tổng quan kiến trúc & quy trình nghiệp vụ.
- `SYSTEM_PROMPTS.md`: Bộ System Prompts chuẩn hóa (Chat, RAG, JSON Extractor).
- `RAG_PRICING_ENGINE.md`: Tài liệu quy tắc tính cước, quy đổi khối lượng & Bảng giá chuẩn.
- `ZALO_WEBHOOK_INTEGRATION.md`: Hướng dẫn cấu hình Nginx, SSL, Webhook Zalo OA & DCHub Portal API.
