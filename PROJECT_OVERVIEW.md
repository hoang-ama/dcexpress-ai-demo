# DC EXPRESS AI AGENT - DỰ ÁN TỰ ĐỘNG HÓA CSKH & TẠO ĐƠN AUTOMATION

## 1. TỔNG QUAN DỰ ÁN & BỐI CẢNH NGHIỆP VỤ
- **Doanh nghiệp**: DC Express (Đi Chung Express - `dichung.vn` / `dichungexpress.com`).
- **Mục tiêu**: Tự động hóa luồng CSKH, tiếp nhận thông tin, tính cước RAG, chốt đơn và đẩy Lead tự động vào hệ thống **DCHub Portal** (`portal.dichung.vn`).
- **Kênh tiếp nhận chính**: 
  * Hotline VoIP: `19006022` / `0901778008` (Quản lý qua Asterisk / Caresoft).
  * Zalo OA: Official Account của DC Express.
  * Website Widget: `dichung.vn` / `dichungexpress.com`.

---

## 2. QUY TRÌNH XỬ LÝ 5 NHÓM THÔNG TIN ĐƠN HÀNG (SLOT FILLING)
AI Agent chịu trách nhiệm thu thập đầy đủ 5 nhóm thông tin chuẩn trước khi báo giá và chốt đơn:
1. **Người giao/gửi hàng**: Tên, Số điện thoại, Địa chỉ chi tiết (Số nhà, đường, quận/huyện, tỉnh/TP).
2. **Người nhận hàng**: Tên, Số điện thoại, Địa chỉ chi tiết.
3. **Thông tin hàng hóa**: Tên hàng, Khối lượng (kg), Kích thước (D x R x C cm), Số lượng, Ảnh chụp (nếu có).
4. **Thời gian mong muốn**: Ngày/giờ gửi hàng, Ngày/giờ mong muốn nhận hàng.
5. **Ghi chú vận chuyển**: Bốc xếp, ngõ hẹp, hẹn giờ, giao tầng cao, v.v.

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
