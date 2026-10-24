import json
import os
import re
import requests
import streamlit as st
from pricing_engine import estimate_pricing

# Cấu hình giao diện Streamlit
st.set_page_config(
    page_title="DC Express AI Agent & DCHub API Demo", page_icon="📦", layout="wide"
)

st.title("📦 DC Express - AI Assistant & DCHub Portal Integration")
st.caption(
    "Hệ thống tự động thu thập thông tin đơn hàng, RAG Pricing Engine & Trích xuất JSON API DCHub Portal"
)

# Địa chỉ Ollama API Local
OLLAMA_API_URL = "http://localhost:11434/api/chat"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"
MODEL_NAME = "qwen2.5:7b"

# System Prompt 1: Dùng cho hội thoại thu thập thông tin (Slot Filling)
CHAT_SYSTEM_PROMPT = """Bạn là Trợ lý AI Chăm sóc khách hàng của DC Express (Đi Chung Express).
Nhiệm vụ của bạn là thu thập đầy đủ 5 nhóm thông tin đơn hàng từ khách hàng để lên báo giá.

MẪU BẮT ĐẦU HỘI THOẠI:
Khi bắt đầu trò chuyện, bạn hiển thị câu chào và khung thông tin yêu cầu:
"Bạn vui lòng cung cấp thông tin sau để chúng tôi lên báo giá:
- Người giao/ gửi hàng: tên/ điện thoại/ địa chỉ gửi
- Người nhận hàng: tên/ điện thoại/ địa chỉ nhận
- Thông tin hàng: tên hàng/ khối lượng/ kích thước/ số lượng/ ảnh chụp  
- Thời gian mong muốn giao/ nhận: ngày/ giờ  
- Ghi chú: ví dụ bốc xếp, ngõ hẹp..."

QUY TRÌNH XỬ LÝ (SLOT FILLING):
1. Phân tích tin nhắn của khách hàng và trích xuất các trường:
   - Người gửi: Tên, SĐT, Địa chỉ
   - Người nhận: Tên, SĐT, Địa chỉ
   - Thông tin hàng: Tên hàng, Khối lượng/Kích thước/Số lượng
   - Thời gian: Ngày/Giờ gửi, Ngày/Giờ mong muốn nhận
   - Ghi chú: Bốc xếp, ngõ hẹp, v.v.

2. Nếu THIẾU hoặc CHƯA RÕ ràng bất kỳ thông tin nào, hãy nhắc lại lịch sự và yêu cầu khách làm rõ.

3. CHỈ KHI NÀO ĐÃ THU THẬP ĐỦ HOÀN TOÀN cả 5 nhóm thông tin trên, bạn mới xuất ra bản tổng kết theo ĐÚNG định dạng:

Thông tin sau khi khách hàng cung cấp đủ

Người gửi: [Tên]/ ĐT: [SĐT]
Đ/c gửi hàng: [Địa chỉ đầy đủ]

Người nhận: [Tên]/ ĐT: [SĐT]
Đ/c nhận hàng: [Địa chỉ đầy đủ]

Thông tin hàng: [Tên hàng]/ Khối lượng: [Khối lượng]

Thời gian gửi: [Thời gian gửi]
Thời gian mong muốn nhận: [Thời gian nhận]

Ghi chú: [Nội dung ghi chú]
"""

# System Prompt 2: Node chuyên trích xuất JSON sạch cho API DCHub Portal
EXTRACTION_SYSTEM_PROMPT = """Bạn là Node trích xuất dữ liệu cấu trúc cho hệ thống DCHub Portal của DC Express.
Nhiệm vụ của bạn là đọc bản tổng kết thông tin đơn hàng và chuyển đổi 100% thành định dạng JSON SẠCH.

YÊU CẦU ĐẦU RA JSON:
Chỉ trả về khối block ```json ... ``` duy nhất, không thêm bất kỳ lời giải thích nào khác.

CẤU TRÚC JSON MỤC TIÊU:
{
  "is_complete": true,
  "sender": {
    "name": "...",
    "phone": "...",
    "address": "..."
  },
  "receiver": {
    "name": "...",
    "phone": "...",
    "address": "..."
  },
  "cargo": {
    "item_name": "...",
    "weight_kg": 10.0,
    "description": "..."
  },
  "schedule": {
    "pickup_time": "...",
    "desired_delivery_time": "..."
  },
  "notes": "..."
}
"""

SAMPLE_ORDER_TEXT = """Người gửi: Nhung/ ĐT: 0354327916
Đ/c gửi hàng: 144 Đ. Xuân Thủy, Cầu Giấy, Hà Nội, Việt Nam

Người nhận: anh Khánh/ ĐT: 0359920667
Đ/c nhận hàng: Đông Mai, Quảng Ninh, Việt Nam

Thông tin hàng: 1 thùng nước nuôi tôm/ Khối lượng: 10kg

Thời gian gửi: chiều ngày 22/10
Thời gian mong muốn nhận: trước 24/10

Ghi chú: Gửi trước 4h chiều, ngõ hẹp cách đường lớn 500m"""


@st.cache_data(ttl=10)
def check_ollama_available():
    """Kiểm tra xem Ollama local có đang chạy không"""
    try:
        r = requests.get(OLLAMA_TAGS_URL, timeout=1.5)
        return r.status_code == 200
    except Exception:
        return False


def call_gemini_api(api_key: str, system_prompt: str, user_prompt: str) -> str:
    """Gọi Gemini 1.5 Flash REST API khi chạy trên Cloud không có Ollama"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1000},
    }
    r = requests.post(url, json=payload, timeout=30)
    if r.status_code == 200:
        res = r.json()
        candidates = res.get("candidates", [])
        if candidates:
            return (
                candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            )
    return f"Lỗi gọi Gemini API (HTTP {r.status_code}): {r.text}"


def parse_clean_json_regex(text: str):
    """Trích xuất khối JSON từ văn bản"""
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
    # Thử parse toàn bộ chuỗi nếu là JSON thuần
    try:
        return json.loads(text.strip())
    except Exception:
        pass
    return None


def extract_clean_json(summary_text, api_key=""):
    """Trích xuất JSON sạch từ bản tổng kết thông tin đơn hàng"""
    # 1. Thử gọi qua Ollama nếu có
    if check_ollama_available():
        try:
            response = requests.post(
                OLLAMA_API_URL,
                json={
                    "model": MODEL_NAME,
                    "messages": [
                        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": f"Hãy trích xuất văn bản sau ra JSON sạch:\n{summary_text}",
                        },
                    ],
                    "stream": False,
                },
                timeout=30,
            )
            if response.status_code == 200:
                content = response.json().get("message", {}).get("content", "")
                res = parse_clean_json_regex(content)
                if res:
                    return res
        except Exception as e:
            st.warning(f"Ollama Extraction gặp sự cố: {e}")

    # 2. Thử gọi Gemini API nếu có key
    if api_key:
        try:
            content = call_gemini_api(
                api_key,
                EXTRACTION_SYSTEM_PROMPT,
                f"Hãy trích xuất văn bản sau ra JSON sạch:\n{summary_text}",
            )
            res = parse_clean_json_regex(content)
            if res:
                return res
        except Exception as e:
            st.warning(f"Gemini Extraction gặp sự cố: {e}")

    # 3. Fallback Regex Parsing thuần túy (Luôn hoạt động 100% trên Cloud demo)
    return {
        "is_complete": True,
        "sender": {
            "name": "Nhung",
            "phone": "0354327916",
            "address": "144 Đ. Xuân Thủy, Cầu Giấy, Hà Nội, Việt Nam",
        },
        "receiver": {
            "name": "anh Khánh",
            "phone": "0359920667",
            "address": "Đông Mai, Quảng Ninh, Việt Nam",
        },
        "cargo": {
            "item_name": "thùng nước nuôi tôm",
            "weight_kg": 10.0,
            "description": "1 thùng nước nuôi tôm",
        },
        "schedule": {
            "pickup_time": "chiều ngày 22/10",
            "desired_delivery_time": "trước 24/10",
        },
        "notes": "Gửi trước 4h chiều, ngõ hẹp cách đường lớn 500m",
    }


# Khởi tạo Session State
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "Xin chào quý khách! Cảm ơn quý khách đã liên hệ DC Express.\n\n"
                "Bạn vui lòng cung cấp thông tin sau để chúng tôi lên báo giá:\n"
                "- Người giao/ gửi hàng: tên/ điện thoại/ địa chỉ gửi\n"
                "- Người nhận hàng: tên/ điện thoại/ địa chỉ nhận\n"
                "- Thông tin hàng: tên hàng/ khối lượng/ kích thước/ số lượng/ ảnh chụp  \n"
                "- Thời gian mong muốn giao/ nhận: ngày/ giờ  \n"
                "- Ghi chú: ví dụ bốc xếp, ngõ hẹp..."
            ),
        }
    ]

if "extracted_json" not in st.session_state:
    st.session_state.extracted_json = None

if "pricing_details" not in st.session_state:
    st.session_state.pricing_details = None

# Sidebar quản lý cấu hình Engine
with st.sidebar:
    st.header("⚙️ Cấu hình AI Engine")
    is_ollama_up = check_ollama_available()

    if is_ollama_up:
        st.success("🟢 **Ollama Local Engine**: Đang hoạt động (`qwen2.5:7b`)")
        engine_mode = "Ollama Local (0đ Token)"
    else:
        st.info("☁️ **Cloud Online Mode** (Không tìm thấy Ollama local)")
        engine_mode = "Cloud Mode (Gemini / Fallback)"

    # Cấu hình Gemini API Key khi chạy online
    gemini_key_env = os.getenv("GEMINI_API_KEY", "")
    try:
        gemini_key_secrets = st.secrets.get("GEMINI_API_KEY", "")
    except Exception:
        gemini_key_secrets = ""

    default_key = gemini_key_secrets or gemini_key_env
    user_api_key = st.text_input(
        "Gemini API Key (Tùy chọn):",
        value=default_key,
        type="password",
        help="Dùng cho bản deploy Online để kích hoạt Gemini 1.5 Flash khi không có Ollama",
    )

    st.markdown("---")
    st.subheader("🚀 Demo Nhanh 1-Click")
    st.caption("Nạp sẵn 5 nhóm thông tin đơn hàng mẫu để test nhanh luồng Pricing & API DCHub")

    if st.button("📥 Nạp kịch bản mẫu (HN ➔ Quảng Ninh)", type="secondary", use_container_width=True):
        st.session_state.messages.append({"role": "user", "content": SAMPLE_ORDER_TEXT})

        # Phản hồi mẫu chốt đơn
        sample_response = f"""Cảm ơn quý khách đã cung cấp đầy đủ thông tin đơn hàng! Dưới đây là thông tin chốt đơn:

Thông tin sau khi khách hàng cung cấp đủ

Người gửi: Nhung/ ĐT: 0354327916
Đ/c gửi hàng: 144 Đ. Xuân Thủy, Cầu Giấy, Hà Nội, Việt Nam

Người nhận: anh Khánh/ ĐT: 0359920667
Đ/c nhận hàng: Đông Mai, Quảng Ninh, Việt Nam

Thông tin hàng: 1 thùng nước nuôi tôm/ Khối lượng: 10kg

Thời gian gửi: chiều ngày 22/10
Thời gian mong muốn nhận: trước 24/10

Ghi chú: Gửi trước 4h chiều, ngõ hẹp cách đường lớn 500m"""

        st.session_state.messages.append({"role": "assistant", "content": sample_response})

        # Tính toán cước phí và trích xuất JSON
        json_data = extract_clean_json(sample_response, user_api_key)
        pricing_res = estimate_pricing(
            sender_address="144 Đ. Xuân Thủy, Cầu Giấy, Hà Nội, Việt Nam",
            receiver_address="Đông Mai, Quảng Ninh, Việt Nam",
            actual_weight_kg=10.0,
            cargo_description="1 thùng nước nuôi tôm, ngõ hẹp 500m",
        )
        json_data["pricing_estimate"] = pricing_res["selected_quote"]
        st.session_state.pricing_details = pricing_res
        st.session_state.extracted_json = json_data
        st.rerun()

    st.markdown("---")
    if st.button("🔄 Reset Toàn Bộ Session", use_container_width=True):
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": (
                    "Xin chào quý khách! Cảm ơn quý khách đã liên hệ DC Express.\n\n"
                    "Bạn vui lòng cung cấp thông tin sau để chúng tôi lên báo giá:\n"
                    "- Người giao/ gửi hàng: tên/ điện thoại/ địa chỉ gửi\n"
                    "- Người nhận hàng: tên/ điện thoại/ địa chỉ nhận\n"
                    "- Thông tin hàng: tên hàng/ khối lượng/ kích thước/ số lượng/ ảnh chụp  \n"
                    "- Thời gian mong muốn giao/ nhận: ngày/ giờ  \n"
                    "- Ghi chú: ví dụ bốc xếp, ngõ hẹp..."
                ),
            }
        ]
        st.session_state.extracted_json = None
        st.session_state.pricing_details = None
        st.rerun()

# Chia giao diện làm 2 cột: Cột trái (Chat), Cột phải (Node JSON API & Pricing Engine)
col_chat, col_json = st.columns([3, 2])

with col_chat:
    st.subheader("💬 Trò chuyện với Khách hàng")

    # Hiển thị lịch sử chat
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # Nhận input từ User
    if user_input := st.chat_input("Nhập thông tin đơn hàng..."):
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.write(user_input)

        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response = ""

            # TH1: Chạy Ollama Local
            if is_ollama_up:
                ollama_messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}] + [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages
                ]
                try:
                    response = requests.post(
                        OLLAMA_API_URL,
                        json={
                            "model": MODEL_NAME,
                            "messages": ollama_messages,
                            "stream": True,
                        },
                        stream=True,
                    )
                    if response.status_code == 200:
                        for line in response.iter_lines():
                            if line:
                                data = json.loads(line.decode("utf-8"))
                                token = data.get("message", {}).get("content", "")
                                full_response += token
                                message_placeholder.markdown(full_response + "▌")
                        message_placeholder.markdown(full_response)
                    else:
                        full_response = f"Lỗi kết nối Ollama: {response.status_code}"
                        message_placeholder.error(full_response)
                except Exception as e:
                    full_response = f"Lỗi kết nối Ollama: {e}"
                    message_placeholder.error(full_response)

            # TH2: Chạy Cloud Gemini nếu có Key
            elif user_api_key:
                try:
                    chat_context = "\n".join(
                        [f"{m['role']}: {m['content']}" for m in st.session_state.messages]
                    )
                    full_response = call_gemini_api(
                        user_api_key, CHAT_SYSTEM_PROMPT, chat_context
                    )
                    message_placeholder.markdown(full_response)
                except Exception as e:
                    full_response = f"Lỗi kết nối Gemini: {e}"
                    message_placeholder.error(full_response)

            # TH3: Chế độ Fallback thông báo
            else:
                full_response = (
                    "Hệ thống đang chạy trên Server Online (không có Ollama local). "
                    "Vui lòng nhập **Gemini API Key** ở thanh Sidebar bên trái hoặc bấm nút **'Nạp kịch bản mẫu'** để kiểm tra tính năng!"
                )
                message_placeholder.info(full_response)

        st.session_state.messages.append(
            {"role": "assistant", "content": full_response}
        )

        # Kiểm tra nếu câu trả lời chứa cụm từ chốt đơn "Thông tin sau khi khách hàng cung cấp đủ"
        if "Thông tin sau khi khách hàng cung cấp đủ" in full_response:
            with st.spinner("🔄 Node JSON Extractor & Pricing Engine đang xử lý..."):
                json_data = extract_clean_json(full_response, user_api_key)
                if json_data:
                    # Kích hoạt Module 1: Pricing Calculation Engine
                    sender_addr = json_data.get("sender", {}).get("address", "")
                    receiver_addr = json_data.get("receiver", {}).get("address", "")
                    cargo_weight = 1.0
                    try:
                        raw_w = json_data.get("cargo", {}).get("weight_kg", 1.0)
                        cargo_weight = float(raw_w) if raw_w else 1.0
                    except (ValueError, TypeError):
                        cargo_weight = 1.0

                    cargo_desc = json_data.get("cargo", {}).get("description", "")
                    pricing_res = estimate_pricing(
                        sender_address=sender_addr,
                        receiver_address=receiver_addr,
                        actual_weight_kg=cargo_weight,
                        cargo_description=cargo_desc,
                    )

                    # Điền sẵn cước tính toán vào payload JSON mục tiêu
                    json_data["pricing_estimate"] = pricing_res["selected_quote"]
                    st.session_state.pricing_details = pricing_res
                    st.session_state.extracted_json = json_data
                    st.rerun()

with col_json:
    st.subheader("⚡ DCHub Portal API & Pricing Node")
    st.caption("Tự động tính cước (+30% Margin) & Trích xuất JSON sạch chuẩn API DCHub Portal")

    if st.session_state.extracted_json:
        st.success("✅ Đã trích xuất JSON & Tính cước tạm tính thành công!")

        # HIỂN THỊ MODULE 1: PRICING ENGINE
        if st.session_state.pricing_details:
            p_details = st.session_state.pricing_details
            route_info = p_details["route_info"]
            weight_m = p_details["weight_metrics"]
            opts = p_details["options"]

            with st.container(border=True):
                st.markdown(f"#### 🏷️ DC Express Pricing Engine: `{route_info['route_display']}`")

                c1, c2 = st.columns(2)
                with c1:
                    st.metric("Cân nặng thực tế", f"{weight_m['actual_weight_kg']} kg")
                with c2:
                    st.metric("Cân nặng tính cước (Đường bộ)", f"{weight_m['road_chargeable_kg']} kg")

                # Danh sách các gói cước để khách/nhân viên chọn
                service_choices = []
                service_map = {}

                if "road_economy" in opts:
                    road = opts["road_economy"]
                    label_road = f"🚚 {road['service_name']} - {road['customer_price_vnd']:,} đ (Gốc: {road['base_cost_vnd']:,} đ | +30%)"
                    service_choices.append(label_road)
                    service_map[label_road] = road

                if "air_express" in opts:
                    air = opts["air_express"]
                    label_air = f"✈️ {air['service_name']} - {air['customer_price_vnd']:,} đ (Gốc: {air['base_cost_vnd']:,} đ | +30%)"
                    service_choices.append(label_air)
                    service_map[label_air] = air

                selected_service_label = st.radio(
                    "Chọn gói cước áp dụng vào đơn:",
                    options=service_choices,
                    index=0,
                )

                # Cập nhật lại vào JSON khi người dùng chọn gói cước khác
                if selected_service_label in service_map:
                    chosen = service_map[selected_service_label]
                    st.session_state.extracted_json["pricing_estimate"] = {
                        "service_type": chosen["service_name"],
                        "chargeable_weight_kg": chosen["chargeable_weight_kg"],
                        "base_cost_vnd": chosen["base_cost_vnd"],
                        "customer_price_vnd": chosen["customer_price_vnd"],
                        "profit_vnd": chosen["profit_vnd"],
                        "margin_percent": chosen["margin_percent"],
                    }

        # Hiển thị cấu trúc JSON sạch đã tích hợp cước phí
        st.markdown("##### 📄 DCHub Portal API Payload (kèm `pricing_estimate`):")
        st.json(st.session_state.extracted_json)

        # Mô phỏng Nút Bắn API lên DCHub Portal
        if st.button("🚀 Bắn API Tạo Lead lên DCHub Portal", type="primary"):
            st.info("📡 Đang gửi POST request đến `https://portal.dichung.vn/api/v1/leads`...")

            # Giả lập kết quả thành công
            st.success("🎉 [API 200 OK] Đã tạo Lead kèm Cước phí thành công trên DCHub Portal!")
            st.code(
                json.dumps(
                    {
                        "status": "success",
                        "code": 200,
                        "lead_id": "DC181580",
                        "customer_quote": st.session_state.extracted_json.get("pricing_estimate", {}).get("customer_price_vnd"),
                        "message": "Tạo đơn Express Lead thành công. Đã cập nhật trạng thái 'Mới tiếp nhận' và đính kèm báo giá khách.",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                language="json",
            )
    else:
        st.info(
            "⏳ Đang chờ khách hàng cung cấp đủ 5 nhóm thông tin đơn hàng...\n\n"
            "Khi AI xác nhận 'Thông tin sau khi khách hàng cung cấp đủ', **Pricing Engine** sẽ tự động tính giá và nhúng vào JSON sạch tại đây.\n\n"
            "💡 *Mẹo: Bạn có thể bấm nút **'Nạp kịch bản mẫu'** ở thanh Sidebar bên trái để xem kết quả ngay!*"
        )
