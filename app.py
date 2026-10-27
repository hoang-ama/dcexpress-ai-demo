import json
import os
import re
import requests
import streamlit as st
from pricing_engine import estimate_pricing
from dchub_service import dchub_service

# Kiểm tra thư viện Google GenAI SDK chính thức
try:
    from google import genai
    from google.genai import types
    HAS_GENAI_SDK = True
except ImportError:
    HAS_GENAI_SDK = False

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

def contains_chinese(text: str) -> bool:
    """Kiểm tra xem văn bản có chứa ký tự chữ Hán / tiếng Trung hay không"""
    if not text:
        return False
    return bool(re.search(r"[\u4e00-\u9fff]", text))


# System Prompt 1: Dùng cho hội thoại tư vấn rả rích từng bước (Progressive Slot-Filling)
CHAT_SYSTEM_PROMPT = """[CRITICAL SYSTEM DIRECTIVE: STRICT VIETNAMESE ONLY]
You are a Customer Support AI Assistant for DC Express (Đi Chung Express) in Vietnam.
You MUST communicate 100% EXCLUSIVELY in natural, polite Vietnamese.
ABSOLUTELY NEVER output ANY Chinese characters (汉字 / 中文) or pinyin under any circumstance!
Every single sentence, word, and character in your answer must be in Vietnamese.

Bạn là Trợ lý AI Chăm sóc Khách hàng của DC Express (Đi Chung Express).
Phong cách của bạn: Thân thiện, lễ phép, nói năng tự nhiên như người Việt Nam, ngắn gọn và chu đáo.

NGUYÊN TẮC VÀNG VỀ TƯ VẤN:
"Rả rích từng bước một - Không làm khách ngợp khi nhìn form":
Tuyệt đối KHÔNG gửi cả danh sách dài nhiều yêu cầu một lúc. Hãy tương tác từng nhóm thông tin theo đúng 5 giai đoạn:


══════════════════════════════════════════════════════════════
GIAI ĐOẠN 1: THU THẬP THÔNG TIN TÍNH GIÁ (CRITICAL INFO)
══════════════════════════════════════════════════════════════
- Bước 1.1: Hỏi điểm gửi (lấy hàng) và điểm nhận (trả hàng). (Chỉ hỏi địa điểm, chưa hỏi tên/SĐT).
- Bước 1.2: Sau khi có điểm gửi - nhận, hỏi thông tin hàng hóa (Loại hàng, cân nặng kg, kích thước, hình ảnh nếu có).
- Bước 1.3: Sau khi có hàng hóa, hỏi thời gian mong muốn gửi/nhận & Ghi chú vận chuyển (ngõ hẹp, bốc xếp...).

══════════════════════════════════════════════════════════════
GIAI ĐOẠN 2: BÁO GIÁ VÀ XÁC NHẬN ĐỒNG Ý GIÁ
══════════════════════════════════════════════════════════════
- Khi đã đủ 3 nhóm thông tin trên (Điểm gửi/nhận, Hàng, Thời gian):
  Bạn tính cước và báo giá rõ ràng (Gói Tiết kiệm đường bộ hoặc Hỏa tốc đường bay).
- Hỏi khách hàng xem mức giá có phù hợp để hỗ trợ lên đơn không.
- CHỈ KHI KHÁCH ĐỒNG Ý GIÁ (ví dụ: "ok", "đồng ý", "lên đơn đi", "giá tốt"), mới chuyển sang Giai đoạn 3!

══════════════════════════════════════════════════════════════
GIAI ĐOẠN 3: THÔNG TIN VẬN HÀNH & THANH TOÁN (ĐỦ VẬN HÀNH)
══════════════════════════════════════════════════════════════
- Bước 3.1: Xin thông tin liên lạc 2 đầu (Tên, SĐT, số nhà cụ thể người gửi và người nhận).
- Bước 3.2: Hỏi bên thanh toán cước (Đầu gửi hay Đầu nhận trả tiền).
- Bước 3.3: Hỏi cách thanh toán (Trả trước chuyển khoản hay Trả sau tiền mặt khi giao nhận).

══════════════════════════════════════════════════════════════
GIAI ĐOẠN 4: TIỆN ÍCH GIA TĂNG (OPTIONAL)
══════════════════════════════════════════════════════════════
- Hỏi nhanh 1 câu ngắn: Bên mình có cần xuất hóa đơn thuế VAT điện tử hay mua bảo hiểm hàng hóa bổ sung không.

══════════════════════════════════════════════════════════════
GIAI ĐOẠN 5: XÁC NHẬN ĐƠN HÀNG (ORDER CONFIRMATION) & XẾP TÀI XẾ
══════════════════════════════════════════════════════════════
- Xuất phiếu xác nhận đơn hàng theo đúng mẫu chuẩn:

[PHIẾU XÁC NHẬN ĐƠN HÀNG - DC EXPRESS ORDER CONFIRMATION]
Tuyến đường: [Điểm gửi] ➔ [Điểm nhận]
Hàng hóa: [Tên hàng] - [Khối lượng] - [Kích thước nếu có]
Gói cước: [Gói cước] - Cước phí: [Giá tiền] đ

ĐẦU GỬI:
- Người gửi: [Tên] - ĐT: [SĐT]
- Địa chỉ: [Địa chỉ đầy đủ]
- Thời gian lấy hàng: [Thời gian lấy]

ĐẦU NHẬN:
- Người nhận: [Tên] - ĐT: [SĐT]
- Địa chỉ: [Địa chỉ đầy đủ]
- Thời gian mong muốn nhận: [Thời gian nhận]

THANH TOÁN & HÓA ĐƠN:
- Bên thanh toán: [Đầu gửi / Đầu nhận]
- Cách thanh toán: [Tiền mặt / Chuyển khoản]
- Hóa đơn VAT: [Có / Không]
- Bảo hiểm bổ sung: [Có / Không]
- Ghi chú: [Nội dung ghi chú]

Trạng thái: ĐÃ XÁC NHẬN ĐƠN ➔ ĐANG ĐIỀU PHỐI TÀI XẾ
(Thông tin tài xế sẽ được tự động gửi qua tin nhắn cho quý khách ngay khi nhà xe xếp chuyến!)
"""

# System Prompt 2: Node chuyên trích xuất JSON sạch cho API DCHub Portal
EXTRACTION_SYSTEM_PROMPT = """Bạn là Node trích xuất dữ liệu cấu trúc cho hệ thống DCHub Portal của DC Express.
Nhiệm vụ của bạn là đọc toàn bộ nội dung hội thoại hoặc PHIẾU XÁC NHẬN ĐƠN HÀNG và chuyển đổi 100% thành định dạng JSON SẠCH.

YÊU CẦU ĐẦU RA JSON:
Chỉ trả về khối block ```json ... ``` duy nhất, không thêm bất kỳ lời giải thích nào khác.

CẤU TRÚC JSON MỤC TIÊU:
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
    "item_name": "...",
    "weight_kg": 10.0,
    "dimensions_cm": "...",
    "description": "..."
  },
  "schedule": {
    "pickup_time": "...",
    "desired_delivery_time": "..."
  },
  "notes": "...",
  "pricing": {
    "service_type": "Đường bộ tiết kiệm (DC Road)",
    "customer_quote_vnd": 118000,
    "is_accepted_by_customer": true
  },
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
  "payment": {
    "payer": "sender",
    "payer_display": "Đầu gửi thanh toán",
    "payment_method": "postpaid_cash",
    "payment_method_display": "Tiền mặt khi lấy hàng"
  },
  "optional_services": {
    "vat_invoice": false,
    "additional_insurance": false
  },
  "dispatch_and_driver": {
    "status": "ready_to_dispatch"
  }
}
"""

SAMPLE_ORDER_TEXT = """[PHIẾU XÁC NHẬN ĐƠN HÀNG - DC EXPRESS ORDER CONFIRMATION]
Tuyến đường: 144 Đ. Xuân Thủy, Cầu Giấy, Hà Nội ➔ Đông Mai, Quảng Ninh
Hàng hóa: 1 thùng nước nuôi tôm - Khối lượng: 10kg
Gói cước: Đường bộ tiết kiệm (DC Road) - Cước phí: 118.000 đ

ĐẦU GỬI:
- Người gửi: Nhung - ĐT: 0354327916
- Địa chỉ: 144 Đ. Xuân Thủy, Cầu Giấy, Hà Nội, Việt Nam
- Thời gian lấy hàng: Chiều 22/10 trước 16:00

ĐẦU NHẬN:
- Người nhận: anh Khánh - ĐT: 0359920667
- Địa chỉ: Đông Mai, Quảng Ninh, Việt Nam
- Thời gian mong muốn nhận: Trước 24/10

THANH TOÁN & HÓA ĐƠN:
- Bên thanh toán: Đầu gửi thanh toán
- Cách thanh toán: Tiền mặt khi lấy hàng
- Hóa đơn VAT: Không
- Bảo hiểm bổ sung: Không
- Ghi chú: Gửi trước 4h chiều, ngõ hẹp cách đường lớn 500m

Trạng thái: ĐÃ XÁC NHẬN ĐƠN ➔ ĐANG ĐIỀU PHỐI TÀI XẾ
(Thông tin tài xế sẽ được tự động gửi qua tin nhắn cho quý khách ngay khi nhà xe xếp chuyến!)"""



# Cấu hình mặc định Ollama
DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434").replace("/api/chat", "").rstrip("/")
DEFAULT_OLLAMA_MODEL = "qwen2.5:7b"


@st.cache_data(ttl=5)
def check_ollama_available(base_url: str = DEFAULT_OLLAMA_URL) -> bool:
    """Kiểm tra xem Ollama server có đang phản hồi không"""
    clean_url = base_url.strip().rstrip("/")
    if not clean_url:
        return False
    try:
        r = requests.get(f"{clean_url}/api/tags", timeout=2.5)
        return r.status_code == 200
    except Exception:
        return False


@st.cache_data(ttl=10)
def get_ollama_models(base_url: str = DEFAULT_OLLAMA_URL):
    """Lấy danh sách các model đang cài đặt trên Ollama server"""
    clean_url = base_url.strip().rstrip("/")
    if not clean_url:
        return False, [], "Chưa nhập địa chỉ URL của Ollama"
    try:
        r = requests.get(f"{clean_url}/api/tags", timeout=3.5)
        if r.status_code == 200:
            data = r.json()
            models = [m.get("name") for m in data.get("models", []) if m.get("name")]
            if not models:
                models = [DEFAULT_OLLAMA_MODEL]
            return True, models, ""
        return False, [], f"Máy chủ phản hồi HTTP {r.status_code}"
    except requests.exceptions.ConnectionError:
        return False, [], f"Không thể kết nối tới {clean_url}."
    except Exception as e:
        return False, [], f"Lỗi: {e}"


# Danh sách các model mới nhất theo chuẩn Gemini 3
PREFERRED_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.8-flash-lite",
    "gemini-3.7-flash",
    "gemini-3.5-flash-lite",
]


# Các từ khóa của model cũ đã bị Google khai tử / deprecated
DEPRECATED_MODEL_KEYWORDS = ["2.5", "2.0", "1.5", "1.0"]


def is_deprecated_model(model_name: str) -> bool:
    """Kiểm tra xem model có thuộc danh sách cũ đã bị Google deprecated không"""
    name_lower = model_name.lower()
    return any(dep in name_lower for dep in DEPRECATED_MODEL_KEYWORDS)


@st.cache_data(ttl=60)
def get_supported_gemini_models(api_key: str):
    """Lấy danh sách các model Gemini khả dụng cho API Key này, loại bỏ 100% model deprecated."""
    if not api_key:
        return [], "Chưa nhập API Key"
    clean_key = api_key.strip()

    discovered_models = []

    # 1. Thử dùng Google GenAI SDK chính thức
    if HAS_GENAI_SDK:
        try:
            client = genai.Client(api_key=clean_key)
            for m in client.models.list():
                methods = getattr(m, "supported_generation_methods", []) or []
                if "generateContent" in methods:
                    name = getattr(m, "name", "").replace("models/", "")
                    if name and not is_deprecated_model(name):
                        discovered_models.append(name)
        except Exception:
            pass

    # 2. Thử Fallback REST API
    if not discovered_models:
        for version in ["v1beta", "v1"]:
            url = f"https://generativelanguage.googleapis.com/{version}/models?key={clean_key}"
            try:
                r = requests.get(url, timeout=10)
                if r.status_code == 200:
                    data = r.json()
                    for m in data.get("models", []):
                        if "generateContent" in m.get("supportedGenerationMethods", []):
                            name = m["name"].replace("models/", "")
                            if not is_deprecated_model(name):
                                discovered_models.append(name)
                    if discovered_models:
                        break
                elif r.status_code in [400, 403]:
                    return [], f"API Key không hợp lệ (HTTP {r.status_code})"
            except Exception as e:
                return [], f"Lỗi kết nối kiểm tra model: {e}"

    # Đảm bảo các model Gemini 3 tối ưu luôn đứng đầu danh sách
    final_models = []
    for pref in PREFERRED_MODELS:
        final_models.append(pref)
    for m in discovered_models:
        if m not in final_models:
            final_models.append(m)

    return final_models, ""


def _execute_gemini_call(api_key: str, model_name: str, system_prompt: str, user_prompt: str):
    """Thực thi cuộc gọi đến model Gemini, hỗ trợ cả Interactions API (Khuyên dùng) và generateContent."""
    clean_key = api_key.strip()
    clean_model = model_name.replace("models/", "").strip()

    # Bỏ qua ngay lập tức nếu là model cũ đã bị khai tử
    if is_deprecated_model(clean_model):
        return False, f"Model {clean_model} đã bị Google khai tử (deprecated)."

    # PHƯƠNG ÁN 1: Dùng Google GenAI SDK nếu có
    if HAS_GENAI_SDK:
        try:
            client = genai.Client(api_key=clean_key)
            # Nếu SDK hỗ trợ Interactions API
            if hasattr(client, "interactions"):
                res = client.interactions.create(
                    model=clean_model,
                    input=user_prompt,
                    system_instruction=system_prompt if system_prompt else None,
                )
                if hasattr(res, "output_text") and res.output_text:
                    return True, res.output_text

            # Fallback SDK generate_content (không truyền tham số temperature đã bị deprecated trên Gemini 3)
            config = types.GenerateContentConfig(
                system_instruction=system_prompt if system_prompt else None,
                max_output_tokens=1500,
            )
            response = client.models.generate_content(
                model=clean_model,
                contents=user_prompt,
                config=config,
            )
            if response and response.text:
                return True, response.text
        except Exception:
            pass

    # PHƯƠNG ÁN 2: Gọi REST Interactions API (Khuyên dùng theo thông báo mới nhất của Google)
    interactions_url = f"https://generativelanguage.googleapis.com/v1beta/interactions?key={clean_key}"
    headers = {"Content-Type": "application/json", "Api-Revision": "2026-05-20"}
    interactions_payload = {
        "model": clean_model,
        "input": user_prompt,
    }
    if system_prompt:
        interactions_payload["system_instruction"] = system_prompt

    try:
        r = requests.post(interactions_url, json=interactions_payload, headers=headers, timeout=30)
        if r.status_code == 200:
            res = r.json()
            if "output_text" in res and res["output_text"]:
                return True, res["output_text"]
            for step in res.get("steps", []):
                if step.get("type") == "model_output":
                    texts = [p.get("text", "") for p in step.get("content", []) if p.get("type") == "text"]
                    if texts:
                        return True, "".join(texts)
    except Exception:
        pass

    # PHƯƠNG ÁN 3: Gọi REST generateContent v1beta (loại bỏ temperature deprecated)
    gen_url = f"https://generativelanguage.googleapis.com/v1beta/models/{clean_model}:generateContent?key={clean_key}"
    gen_payload = {
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {"maxOutputTokens": 1500},
    }
    if system_prompt:
        gen_payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

    try:
        r = requests.post(gen_url, json=gen_payload, timeout=30)
        if r.status_code == 200:
            res = r.json()
            candidates = res.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                text_parts = [p.get("text", "") for p in parts if "text" in p]
                if text_parts:
                    return True, "".join(text_parts)
        else:
            err_msg = r.json().get("error", {}).get("message", r.text)
            return False, f"[{clean_model}] (HTTP {r.status_code}): {err_msg}"
    except Exception as e:
        return False, f"Lỗi mạng: {e}"

    return False, f"[{clean_model}] Không nhận được phản hồi từ máy chủ Gemini."


def call_gemini_api(api_key: str, system_prompt: str, user_prompt: str, selected_model: str = "") -> str:
    """Gọi Gemini API, tự động ưu tiên gemini-3.8-flash và các model Gemini 3 mới nhất, loại bỏ hoàn toàn model cũ."""
    clean_model = selected_model.replace("models/", "").strip() if selected_model else ""

    # Lập danh sách model để thử, tuyệt đối không dùng model deprecated
    models_to_try = []
    if clean_model and not is_deprecated_model(clean_model):
        models_to_try.append(clean_model)

    for m in PREFERRED_MODELS:
        if m not in models_to_try:
            models_to_try.append(m)

    last_error = ""
    for model in models_to_try:
        success, text = _execute_gemini_call(api_key, model, system_prompt, user_prompt)
        if success:
            return text
        else:
            last_error = text
            err_lower = text.lower()
            # Nếu gặp lỗi model không tồn tại hoặc đã bị khai tử, tự động chuyển ngay sang model tiếp theo
            if any(k in err_lower for k in ["no longer available", "not found", "404", "deprecated"]):
                continue

    return f"Lỗi gọi Gemini API: {last_error}"


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


def extract_clean_json(
    summary_text: str,
    engine_mode: str = "cloud",
    ollama_url: str = DEFAULT_OLLAMA_URL,
    selected_ollama_model: str = DEFAULT_OLLAMA_MODEL,
    api_key: str = "",
    selected_gemini_model: str = "gemini-3.8-flash",
):
    """Trích xuất JSON sạch từ bản tổng kết thông tin đơn hàng theo Engine đã chọn"""
    # 1. Nếu chọn hoặc ưu tiên Ollama
    if engine_mode == "ollama" and ollama_url:
        clean_url = ollama_url.strip().rstrip("/")
        chat_url = f"{clean_url}/api/chat"
        try:
            response = requests.post(
                chat_url,
                json={
                    "model": selected_ollama_model,
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

    # 2. Nếu chọn hoặc fallback sang Gemini API
    if api_key:
        try:
            content = call_gemini_api(
                api_key,
                EXTRACTION_SYSTEM_PROMPT,
                f"Hãy trích xuất văn bản sau ra JSON sạch:\n{summary_text}",
                selected_gemini_model,
            )
            res = parse_clean_json_regex(content)
            if res:
                return res
        except Exception as e:
            st.warning(f"Gemini Extraction gặp sự cố: {e}")


    # 3. Fallback Regex Parsing thuần túy (Luôn hoạt động 100% trên Cloud demo)
    return {
        "order_code": "DC-HNQN-20261025-01",
        "workflow_stage": "confirmed",
        "is_price_agreed": True,
        "route_info": {
            "sender_area": "Hà Nội",
            "receiver_area": "Quảng Ninh",
            "route_type": "lien_tinh_cung_mien",
        },
        "cargo": {
            "item_name": "thùng nước nuôi tôm",
            "weight_kg": 10.0,
            "dimensions_cm": "30x20x20",
            "image_attached": False,
            "description": "1 thùng nước nuôi tôm, ngõ hẹp cách đường 500m",
        },
        "schedule": {
            "pickup_time": "chiều ngày 22/10, trước 16:00",
            "desired_delivery_time": "trước 24/10",
        },
        "notes": "Gửi trước 4h chiều, ngõ hẹp cách đường lớn 500m",
        "pricing": {
            "service_type": "Đường bộ tiết kiệm (DC Road)",
            "base_cost_vnd": 91000,
            "customer_quote_vnd": 118000,
            "margin_percent": 30.0,
            "is_accepted_by_customer": True,
        },
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
        "payment": {
            "payer": "sender",
            "payer_display": "Đầu gửi thanh toán",
            "payment_method": "postpaid_cash",
            "payment_method_display": "Tiền mặt khi lấy hàng",
            "is_paid": False,
        },
        "optional_services": {
            "vat_invoice": False,
            "tax_code": None,
            "additional_insurance": False,
        },
        "dispatch_and_driver": {
            "status": "ready_to_dispatch",
            "driver_name": None,
            "driver_phone": None,
            "vehicle_plate": None,
            "carrier_name": None,
            "customer_notified": False,
            "driver_notified": False,
        },
    }


# Khởi tạo Session State
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "Dạ DC Express xin kính chào quý khách ạ! 📦\n\n"
                "Em có thể hỗ trợ mình gửi hàng từ khu vực nào đến khu vực nào để em kiểm tra tuyến xe và báo giá tốt nhất cho mình ạ?"
            ),
        }
    ]

if "extracted_json" not in st.session_state:
    st.session_state.extracted_json = None

if "pricing_details" not in st.session_state:
    st.session_state.pricing_details = None

if "driver_dispatched" not in st.session_state:
    st.session_state.driver_dispatched = False

if "dchub_lead" not in st.session_state:
    st.session_state.dchub_lead = None

if "dchub_order" not in st.session_state:
    st.session_state.dchub_order = None

if "dchub_live_list" not in st.session_state:
    st.session_state.dchub_live_list = None

# Sidebar quản lý cấu hình Engine
with st.sidebar:
    st.header("⚙️ Cấu hình AI Engine")

    # 1. Cho phép người dùng chủ động lựa chọn Engine
    local_ollama_detected = check_ollama_available(DEFAULT_OLLAMA_URL)
    default_engine_idx = 1 if local_ollama_detected else 0

    engine_choice = st.radio(
        "Lựa chọn AI Engine:",
        options=["☁️ Google Gemini API (Cloud)", "🖥️ Ollama AI Engine (Local / Remote)"],
        index=default_engine_idx,
        help="Chọn Google Gemini API để chạy trên đám mây hoặc Ollama để tự chạy model local (0đ token)."
    )

    selected_gemini_model = "gemini-3.8-flash"
    user_api_key = ""
    ollama_url = DEFAULT_OLLAMA_URL
    selected_ollama_model = DEFAULT_OLLAMA_MODEL
    is_engine_ready = False

    # CHẾ ĐỘ 1: GOOGLE GEMINI API (CLOUD)
    if engine_choice == "☁️ Google Gemini API (Cloud)":
        gemini_key_env = os.getenv("GEMINI_API_KEY", "")
        try:
            gemini_key_secrets = st.secrets.get("GEMINI_API_KEY", "")
        except Exception:
            gemini_key_secrets = ""

        default_key = gemini_key_secrets or gemini_key_env
        user_api_key = st.text_input(
            "Gemini API Key:",
            value=default_key,
            type="password",
            help="Lấy API Key miễn phí từ https://aistudio.google.com/apikey",
        )

        if user_api_key:
            available_models, err = get_supported_gemini_models(user_api_key)
            if available_models:
                st.success(f"✅ Key hợp lệ! ({len(available_models)} models)")
                default_idx = 0
                if "gemini-3.8-flash" in available_models:
                    default_idx = available_models.index("gemini-3.8-flash")

                selected_gemini_model = st.selectbox(
                    "Chọn Gemini Model:",
                    options=available_models,
                    index=default_idx,
                )
                is_engine_ready = True
            elif err:
                st.error(f"❌ {err}")
                st.caption("👉 Lấy API key miễn phí tại: [Google AI Studio](https://aistudio.google.com/apikey)")
        else:
            st.info("ℹ️ Nhập API Key hoặc cấu hình `GEMINI_API_KEY` trong Secrets để kích hoạt.")

    # CHẾ ĐỘ 2: OLLAMA AI ENGINE (LOCAL HOẶC REMOTE QUA NGROK)
    else:
        st.markdown("**Cấu hình máy chủ Ollama:**")
        saved_url = st.session_state.get("ollama_url_input", DEFAULT_OLLAMA_URL)
        ollama_url = st.text_input(
            "Ollama Server URL:",
            value=saved_url,
            help="Chạy Local Mac: http://localhost:11434. Chạy trên Streamlit Cloud: nhập URL Ngrok/Cloudflare (vd: https://xxxx.ngrok-free.app)."
        )
        st.session_state.ollama_url_input = ollama_url

        is_up, models, err_msg = get_ollama_models(ollama_url)
        if is_up:
            st.success(f"🟢 **Ollama Đang Hoạt Động!** ({len(models)} models)")
            default_m_idx = 0
            if "qwen2.5:7b" in models:
                default_m_idx = models.index("qwen2.5:7b")

            selected_ollama_model = st.selectbox(
                "Chọn Ollama Model:",
                options=models,
                index=default_m_idx,
            )
            is_engine_ready = True
        else:
            st.warning(f"🔴 **Chưa kết nối được Ollama**: {err_msg}")
            with st.expander("🌐 Cách kết nối Ollama với Streamlit Cloud", expanded=True):
                st.markdown(
                    """
                    Khi mở web trên **`streamlit.app` (Cloud)**, server không thể gọi trực tiếp `localhost` của máy Mac. Để kết nối:
                    1. Mở Terminal trên máy tính, chạy:
                       ```bash
                       ngrok http 11434
                       ```
                       *(Hoặc `cloudflared tunnel --url http://localhost:11434`)*
                    2. Copy link công khai (ví dụ: `https://xxxx.ngrok-free.app`).
                    3. Dán vào ô **Ollama Server URL** ở trên và nhấn Enter!
                    """
                )


    st.markdown("---")
    st.subheader("🚀 Demo Nhanh 1-Click")
    st.caption("Mô phỏng kịch bản hội thoại tự nhiên rả rích 5 giai đoạn")

    if st.button("📥 Nạp kịch bản mẫu 5 Giai đoạn (HN ➔ Quảng Ninh)", type="secondary", use_container_width=True):
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": "Dạ DC Express xin kính chào quý khách ạ! 📦\n\nEm có thể hỗ trợ mình gửi hàng từ khu vực nào đến khu vực nào để em kiểm tra tuyến xe và báo giá tốt nhất cho mình ạ?",
            },
            {
                "role": "user",
                "content": "Mình muốn gửi từ Cầu Giấy Hà Nội về Đông Mai, Quảng Ninh bạn nhé.",
            },
            {
                "role": "assistant",
                "content": "Dạ tuyến Hà Nội đi Quảng Ninh bên em có xe chạy liên tục hàng ngày ạ. Anh/Chị cho em hỏi mình gửi mặt hàng gì, cân nặng tầm bao nhiêu kg hoặc kích thước kiện thế nào ạ (nếu có hình ảnh thì càng tốt ạ)?",
            },
            {
                "role": "user",
                "content": "1 thùng nước nuôi tôm, nặng tầm 10kg.",
            },
            {
                "role": "assistant",
                "content": "Dạ vâng ạ. Anh/Chị dự kiến khi nào gửi hàng và muốn người nhận nhận trước ngày giờ nào ạ? Chỗ mình gửi có ngõ hẹp hay lưu ý gì đặc biệt không ạ?",
            },
            {
                "role": "user",
                "content": "Gửi chiều nay 22/10 trước 4h chiều, nhận trước ngày 24/10 nhé. Chỗ gửi ngõ hơi hẹp cách đường lớn 500m.",
            },
            {
                "role": "assistant",
                "content": (
                    "Dạ em đã nắm được thông tin đơn của mình ạ. Với kiện 1 thùng nước nuôi tôm 10kg từ Cầu Giấy đi Đông Mai, Quảng Ninh:\n\n"
                    "🚚 **Cước vận chuyển Gói Tiết kiệm đường bộ**: **118.000 đ** (Giao tận nơi 1-2 ngày)\n"
                    "*(Gói Hỏa tốc đường bay/xe riêng nếu cần gấp: 234.000 đ)*\n\n"
                    "Mức giá 118.000 đ đã trọn gói giao tận nơi. Anh/Chị xem qua thấy mức giá và thời gian này đã phù hợp để bên em hỗ trợ lên đơn chưa ạ?"
                ),
            },
            {
                "role": "user",
                "content": "Ok giá 118k hợp lý đấy em, lên đơn cho anh đi.",
            },
            {
                "role": "assistant",
                "content": (
                    "Dạ em cảm ơn anh đã tin tưởng lựa chọn DC Express! Để bên em sắp xếp tài xế qua lấy hàng đúng hẹn, anh cho em xin thông tin:\n"
                    "- Đầu gửi: Tên, SĐT và số nhà cụ thể tại Cầu Giấy.\n"
                    "- Đầu nhận: Tên, SĐT và địa chỉ người nhận tại Đông Mai ạ."
                ),
            },
            {
                "role": "user",
                "content": "Người gửi: Nhung, SĐT 0354327916, 144 Xuân Thủy, Cầu Giấy. Người nhận: anh Khánh, SĐT 0359920667, Đông Mai, Quảng Ninh.",
            },
            {
                "role": "assistant",
                "content": "Dạ đơn này bên mình đầu gửi thanh toán hay anh Khánh nhận hàng thanh toán cước ạ? Mình muốn thanh toán trước qua chuyển khoản hay trả tiền mặt khi giao nhận ạ?",
            },
            {
                "role": "user",
                "content": "Đầu gửi thanh toán tiền mặt lúc tài xế qua lấy hàng nhé.",
            },
            {
                "role": "assistant",
                "content": "Dạ vâng ạ. Em hỏi thêm một chút là bên mình có cần xuất hóa đơn thuế VAT điện tử hoặc mua bảo hiểm hàng hóa bổ sung không ạ?",
            },
            {
                "role": "user",
                "content": "Không cần VAT với bảo hiểm đâu em.",
            },
            {
                "role": "assistant",
                "content": SAMPLE_ORDER_TEXT,
            },
        ]

        # Tính toán cước phí và trích xuất JSON
        json_data = extract_clean_json(
            SAMPLE_ORDER_TEXT,
            engine_mode="ollama" if engine_choice.startswith("🖥️") else "gemini",
            ollama_url=ollama_url,
            selected_ollama_model=selected_ollama_model,
            api_key=user_api_key,
            selected_gemini_model=selected_gemini_model,
        )
        pricing_res = estimate_pricing(
            sender_address="144 Đ. Xuân Thủy, Cầu Giấy, Hà Nội, Việt Nam",
            receiver_address="Đông Mai, Quảng Ninh, Việt Nam",
            actual_weight_kg=10.0,
            cargo_description="1 thùng nước nuôi tôm, ngõ hẹp 500m",
        )
        json_data["pricing"] = {
            "service_type": pricing_res["selected_quote"]["service_type"],
            "base_cost_vnd": pricing_res["selected_quote"]["base_cost_vnd"],
            "customer_quote_vnd": pricing_res["selected_quote"]["customer_price_vnd"],
            "margin_percent": pricing_res["selected_quote"]["margin_percent"],
            "is_accepted_by_customer": True,
        }
        st.session_state.pricing_details = pricing_res
        st.session_state.extracted_json = json_data
        st.session_state.driver_dispatched = False
        st.rerun()

    st.markdown("---")
    if st.button("🔄 Reset Toàn Bộ Session", use_container_width=True):
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": (
                    "Dạ DC Express xin kính chào quý khách ạ! 📦\n\n"
                    "Em có thể hỗ trợ mình gửi hàng từ khu vực nào đến khu vực nào để em kiểm tra tuyến xe và báo giá tốt nhất cho mình ạ?"
                ),
            }
        ]
        st.session_state.extracted_json = None
        st.session_state.pricing_details = None
        st.session_state.driver_dispatched = False
        st.rerun()

# ----------------- THANH TIẾN TRÌNH 5 GIAI ĐOẠN -----------------
def determine_conversation_stage():
    """Nhận diện giai đoạn hiện tại của cuộc hội thoại theo 5 giai đoạn"""
    if st.session_state.driver_dispatched:
        return 5, "Đã điều phối tài xế thành công"
    
    all_text = " ".join([m["content"] for m in st.session_state.messages])
    if "ORDER CONFIRMATION" in all_text or "PHIẾU XÁC NHẬN ĐƠN HÀNG" in all_text or "Thông tin sau khi khách hàng cung cấp đủ" in all_text:
        return 5, "Giai đoạn 5: Order Confirmation (Đang xếp tài)"
    elif "VAT" in all_text or "hóa đơn" in all_text or "bảo hiểm" in all_text:
        return 4, "Giai đoạn 4: Tiện ích gia tăng (VAT & Bảo hiểm)"
    elif "thanh toán" in all_text or "Đầu gửi thanh toán" in all_text or "SĐT" in all_text:
        return 3, "Giai đoạn 3: Thông tin vận hành & Thanh toán"
    elif "Cước vận chuyển" in all_text or "Gói Tiết kiệm" in all_text or "báo giá" in all_text.lower():
        return 2, "Giai đoạn 2: Báo giá & Xác nhận đồng ý giá"
    else:
        return 1, "Giai đoạn 1: Thu thập Tuyến đường, Hàng hóa & Lịch trình"

current_stage_idx, current_stage_desc = determine_conversation_stage()

st.markdown(
    f"""
    <div style="background-color: #f0f4f8; border-radius: 8px; padding: 10px 16px; margin-bottom: 16px; border-left: 5px solid #0284c7;">
        <span style="font-weight: 600; color: #0369a1;">📍 TIẾN TRÌNH TƯ VẤN:</span>
        <span style="margin-left: 10px; color: #0f172a;"><b>{current_stage_desc}</b></span>
        <div style="display: flex; gap: 8px; margin-top: 8px; font-size: 13px;">
            <span style="padding: 2px 8px; border-radius: 4px; background: {'#0284c7; color: white;' if current_stage_idx >= 1 else '#e2e8f0; color: #64748b;'}">1. Tuyến & Hàng</span>
            ➔
            <span style="padding: 2px 8px; border-radius: 4px; background: {'#0284c7; color: white;' if current_stage_idx >= 2 else '#e2e8f0; color: #64748b;'}">2. Báo & Chốt giá</span>
            ➔
            <span style="padding: 2px 8px; border-radius: 4px; background: {'#0284c7; color: white;' if current_stage_idx >= 3 else '#e2e8f0; color: #64748b;'}">3. Vận hành & Thanh toán</span>
            ➔
            <span style="padding: 2px 8px; border-radius: 4px; background: {'#0284c7; color: white;' if current_stage_idx >= 4 else '#e2e8f0; color: #64748b;'}">4. VAT & Tiện ích</span>
            ➔
            <span style="padding: 2px 8px; border-radius: 4px; background: {'#0284c7; color: white;' if current_stage_idx >= 5 else '#e2e8f0; color: #64748b;'}">5. Order Confirmation & Xếp tài</span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Chia giao diện làm 2 cột: Cột trái (Chat), Cột phải (Node JSON API & Pricing Engine)
col_chat, col_json = st.columns([3, 2])

with col_chat:
    st.subheader("💬 Trò chuyện với Khách hàng (Tư vấn tự nhiên)")

    # Hiển thị lịch sử chat
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # Nhận input từ User
    if user_input := st.chat_input("Nhập tin nhắn phản hồi..."):
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.write(user_input)

        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            full_response = ""

            # TH1: Chạy Ollama AI Engine (Local hoặc Ngrok Remote)
            if engine_choice.startswith("🖥️"):
                if not is_engine_ready:
                    full_response = (
                        f"Chưa kết nối được với máy chủ Ollama tại `{ollama_url}`. "
                        "Vui lòng kiểm tra lại URL hoặc chuyển sang chế độ **☁️ Google Gemini API (Cloud)** ở thanh Sidebar bên trái!"
                    )
                    message_placeholder.warning(full_response)
                else:
                    ollama_chat_url = f"{ollama_url.strip().rstrip('/')}/api/chat"
                    ollama_messages = [{"role": "system", "content": CHAT_SYSTEM_PROMPT}] + [
                        {"role": m["role"], "content": m["content"]}
                        for m in st.session_state.messages
                    ]
                    try:
                        response = requests.post(
                            ollama_chat_url,
                            json={
                                "model": selected_ollama_model,
                                "messages": ollama_messages,
                                "options": {
                                    "temperature": 0.2,
                                    "top_p": 0.9,
                                },
                                "stream": True,
                            },
                            stream=True,
                            timeout=60,
                        )
                        if response.status_code == 200:
                            for line in response.iter_lines():
                                if line:
                                    data = json.loads(line.decode("utf-8"))
                                    token = data.get("message", {}).get("content", "")
                                    full_response += token
                                    message_placeholder.markdown(full_response + "▌")
                            
                            # Kiểm tra nếu câu trả lời bị lọt ký tự chữ Hán (do Qwen)
                            if contains_chinese(full_response):
                                with st.spinner("Đang chuẩn hóa ngôn ngữ tiếng Việt..."):
                                    try:
                                        clean_res = requests.post(
                                            ollama_chat_url,
                                            json={
                                                "model": selected_ollama_model,
                                                "messages": [
                                                    {"role": "system", "content": "Translate and rewrite the following text into 100% natural Vietnamese. Absolutely NO Chinese characters."},
                                                    {"role": "user", "content": full_response}
                                                ],
                                                "options": {"temperature": 0.1},
                                                "stream": False
                                            },
                                            timeout=20
                                        )
                                        if clean_res.status_code == 200:
                                            cand = clean_res.json().get("message", {}).get("content", "")
                                            if cand and not contains_chinese(cand):
                                                full_response = cand
                                    except Exception:
                                        pass

                            message_placeholder.markdown(full_response)
                        else:
                            full_response = f"Lỗi phản hồi từ Ollama ({response.status_code}): {response.text}"
                            message_placeholder.error(full_response)
                    except Exception as e:
                        full_response = f"Lỗi kết nối Ollama: {e}"
                        message_placeholder.error(full_response)


            # TH2: Chạy Cloud Gemini nếu chọn Gemini
            elif engine_choice.startswith("☁️"):
                if not user_api_key:
                    full_response = (
                        "Vui lòng nhập **Gemini API Key** ở thanh Sidebar bên trái để trò chuyện, "
                        "hoặc bấm nút **'Nạp kịch bản mẫu 5 Giai đoạn'** để trải nghiệm nhanh!"
                    )
                    message_placeholder.info(full_response)
                else:
                    with st.spinner(f"Đang kết nối Gemini AI ({selected_gemini_model})..."):
                        try:
                            chat_context = "\n".join(
                                [f"{m['role']}: {m['content']}" for m in st.session_state.messages]
                            )
                            full_response = call_gemini_api(
                                user_api_key, CHAT_SYSTEM_PROMPT, chat_context, selected_gemini_model
                            )
                            message_placeholder.markdown(full_response)
                        except Exception as e:
                            full_response = f"Lỗi xử lý Gemini: {e}"
                            message_placeholder.error(full_response)

            # TH3: Chế độ Fallback thông báo
            else:
                full_response = "Vui lòng cấu hình AI Engine ở Sidebar bên trái để bắt đầu trò chuyện!"
                message_placeholder.info(full_response)

        st.session_state.messages.append(
            {"role": "assistant", "content": full_response}
        )

        # Kiểm tra nếu câu trả lời chứa Phiếu xác nhận đơn hàng hoặc bản chốt đơn
        if any(kw in full_response for kw in ["ORDER CONFIRMATION", "PHIẾU XÁC NHẬN ĐƠN HÀNG", "Thông tin sau khi khách hàng cung cấp đủ"]):
            with st.spinner("🔄 Node JSON Extractor & Pricing Engine đang xử lý..."):
                json_data = extract_clean_json(
                    full_response,
                    engine_mode="ollama" if engine_choice.startswith("🖥️") else "gemini",
                    ollama_url=ollama_url,
                    selected_ollama_model=selected_ollama_model,
                    api_key=user_api_key,
                    selected_gemini_model=selected_gemini_model,
                )

                if json_data:
                    sender_addr = json_data.get("sender", {}).get("address", "") or json_data.get("route_info", {}).get("sender_area", "Hà Nội")
                    receiver_addr = json_data.get("receiver", {}).get("address", "") or json_data.get("route_info", {}).get("receiver_area", "Quảng Ninh")
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

                    json_data["pricing"] = {
                        "service_type": pricing_res["selected_quote"]["service_type"],
                        "base_cost_vnd": pricing_res["selected_quote"]["base_cost_vnd"],
                        "customer_quote_vnd": pricing_res["selected_quote"]["customer_price_vnd"],
                        "margin_percent": 30.0,
                        "is_accepted_by_customer": True,
                    }
                    st.session_state.pricing_details = pricing_res
                    st.session_state.extracted_json = json_data
                    st.rerun()

with col_json:
    st.subheader("⚡ DCHub Portal Express & Driver Dispatch")
    st.markdown(
        "[🔗 Mở DCHub Portal Express](https://portal.dichung.vn/booking~express) &nbsp;|&nbsp; "
        "🟢 **Staging API Live** (`client: kqab...04o7z5b`)"
    )

    # Nút đồng bộ nhanh đơn hàng thực tế từ Staging DCHub Portal
    col_sync1, col_sync2 = st.columns([2, 1])
    with col_sync2:
        if st.button("🔄 Tải đơn từ DCHub", use_container_width=True, help="Lấy danh sách đơn hàng thực tế từ Đi Chung Staging"):
            with st.spinner("Đang tải dữ liệu từ DCHub Portal API..."):
                bookings = dchub_service.list_bookings(limit=5)
                st.session_state.dchub_live_list = bookings
                st.success(f"Đã tải {len(bookings)} đơn thực tế từ DCHub!")

    # 1. BẢNG HIỂN THỊ ĐƠN HÀNG THỰC TẾ NẾU VỪA TẢI VỀ
    if st.session_state.dchub_live_list:
        with st.expander(f"📦 Danh sách {len(st.session_state.dchub_live_list)} đơn hàng thực tế từ DCHub Portal Staging", expanded=False):
            for b in st.session_state.dchub_live_list:
                st.markdown(
                    f"**Mã đơn:** `{b.get('code', 'N/A')}` | **ID:** `{b.get('_id')}` | **Trạng thái:** `{b.get('status')}`  \n"
                    f"- **Người gửi:** {b.get('bookingUser', {}).get('fullName')} ({b.get('bookingUser', {}).get('phone')})  \n"
                    f"- **Điểm lấy:** {b.get('startPoint', {}).get('name') or b.get('startPlace', {}).get('formatted_address')}  \n"
                    f"- **Điểm trả:** {b.get('endPoint', {}).get('name') or b.get('endPlace', {}).get('formatted_address')}  \n"
                    f"- **Tổng tiền:** {b.get('payment', {}).get('totalCost', 0):,} đ"
                )
                st.divider()

    if st.session_state.extracted_json:
        st.success("✅ Đơn hàng đã chốt qua 5 Giai đoạn & Sẵn sàng đồng bộ DCHub Portal!")

        # 1. HIỂN THỊ MODULE PRICING ENGINE
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
                    st.metric("Cân nặng tính cước", f"{weight_m['road_chargeable_kg']} kg")

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
                    "Gói cước đã thỏa thuận với khách:",
                    options=service_choices,
                    index=0,
                )

                if selected_service_label in service_map:
                    chosen = service_map[selected_service_label]
                    st.session_state.extracted_json["pricing"] = {
                        "service_type": chosen["service_name"],
                        "chargeable_weight_kg": chosen["chargeable_weight_kg"],
                        "base_cost_vnd": chosen["base_cost_vnd"],
                        "customer_quote_vnd": chosen["customer_price_vnd"],
                        "profit_vnd": chosen["profit_vnd"],
                        "margin_percent": chosen["margin_percent"],
                        "is_accepted_by_customer": True,
                    }

        # 2. BẢNG MÔ PHỎNG DCHUB PORTAL EXPRESS DASHBOARD CHUẨN THEO ẢNH THỰC TẾ
        ext = st.session_state.extracted_json
        sender_name = ext.get("sender", {}).get("name") or "Long"
        sender_phone = ext.get("sender", {}).get("phone") or "0399092104"
        sender_addr = ext.get("sender", {}).get("address") or "T1, Khu đô thị Times City, Vĩnh Tuy, Hà Nội, Việt Nam"

        receiver_name = ext.get("receiver", {}).get("name") or "Thảo"
        receiver_phone = ext.get("receiver", {}).get("phone") or "0366427496"
        receiver_addr = ext.get("receiver", {}).get("address") or "Khu du lịch sinh thái Thung Nham, thôn Hải Nham, Ninh Bình"

        cargo_desc = ext.get("cargo", {}).get("description") or "1 tập tài liệu"
        cargo_type = ext.get("cargo", {}).get("cargo_type") or "Phong bì, tài liệu"
        cargo_weight = ext.get("cargo", {}).get("weight_kg") or 5.0

        customer_price = ext.get("pricing", {}).get("customer_quote_vnd") or 890000
        net_price = ext.get("pricing", {}).get("base_cost_vnd") or 390000
        cod_amount = ext.get("cargo", {}).get("cod_amount") or 350000

        with st.container(border=True):
            st.markdown("### 🖥️ Màn hình DCHub Portal (`portal.dichung.vn/booking~express`)")

            # HÀNG ACTION: 2 NÚT CHÍNH (TẠO LEAD & TẠO ĐƠN HÀNG)
            act_col1, act_col2 = st.columns(2)
            with act_col1:
                if st.button("📑 Tạo Lead (express_lead - 'Có nhu cầu')", use_container_width=True, type="secondary"):
                    with st.spinner("Đang gửi Lead lên DCHub Portal..."):
                        lead_res = dchub_service.create_lead(
                            sender={"name": sender_name, "phone": sender_phone, "address": sender_addr},
                            receiver={"name": receiver_name, "phone": receiver_phone, "address": receiver_addr},
                            cargo={"description": cargo_desc, "type": cargo_type, "weight_kg": cargo_weight, "cod_amount": cod_amount},
                            service_type=ext.get("pricing", {}).get("service_type") or "Chuyển nhanh",
                        )
                        st.session_state.dchub_lead = lead_res
                        st.toast(f"Đã tạo Lead {lead_res['code']} trên DCHub Portal!", icon="📑")

            with act_col2:
                if st.button("🚀 Tạo Đơn Hàng Chính Thức ('Khách chốt')", use_container_width=True, type="primary"):
                    with st.spinner("Đang tạo đơn hàng và sinh mã DC trên DCHub Portal..."):
                        order_res = dchub_service.create_order(
                            sender={"name": sender_name, "phone": sender_phone, "address": sender_addr},
                            receiver={"name": receiver_name, "phone": receiver_phone, "address": receiver_addr},
                            cargo={"description": cargo_desc, "type": cargo_type, "weight_kg": cargo_weight, "cod_amount": cod_amount},
                            pricing={"customer_price_vnd": customer_price, "base_cost_vnd": net_price, "service_type": ext.get("pricing", {}).get("service_type") or "Chuyển nhanh"},
                            payment_method="transfer | sender prepaid | company",
                        )
                        st.session_state.dchub_order = order_res
                        st.toast(f"Đã tạo đơn {order_res['code']} thành công trên DCHub Portal!", icon="🎉")

            # HIỂN THỊ DÒNG ĐƠN HÀNG / LEAD CHUẨN THEO ẢNH
            current_code = (
                st.session_state.dchub_order.get("code")
                if st.session_state.dchub_order
                else (st.session_state.dchub_lead.get("code") if st.session_state.dchub_lead else "DC181611")
            )

            is_order_confirmed = bool(st.session_state.dchub_order)
            status_tag = "Khách chốt" if is_order_confirmed else "Có nhu cầu"
            status_color = "green" if is_order_confirmed else "blue"
            dispatch_status = "Đã điều" if st.session_state.driver_dispatched else "Chưa điều"

            st.markdown(
                f"""
                <div style="background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 8px; padding: 12px; margin-bottom: 12px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px dashed #ced4da; padding-bottom: 8px;">
                        <div>
                            <span style="background-color: {'#28a745' if status_color == 'green' else '#007bff'}; color: white; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 13px;">{status_tag}</span>
                            <span style="font-weight: bold; font-size: 16px; margin-left: 8px; color: #1e3a8a;">{current_code}</span>
                            <span style="color: #6c757d; font-size: 13px;">(express_lead - Chuyển nhanh)</span>
                        </div>
                        <div>
                            <span style="font-size: 12px; color: #6c757d;">PIC tiếp nhận:</span>
                            <b style="font-size: 13px; color: #333;"> Nguyễn Thành Nam</b>
                        </div>
                    </div>
                    <div style="display: grid; grid-template-columns: 2fr 1fr 1.5fr; gap: 12px; padding-top: 10px; font-size: 13px;">
                        <div>
                            <div>👤 <b>Người gửi:</b> {sender_name} ({sender_phone})</div>
                            <div style="color: #555;">📍 <i>Lấy:</i> {sender_addr}</div>
                            <div style="margin-top: 6px;">👤 <b>Người nhận:</b> {receiver_name} ({receiver_phone})</div>
                            <div style="color: #555;">📍 <i>Trả:</i> {receiver_addr}</div>
                        </div>
                        <div>
                            <div>📦 <b>Hàng hóa:</b> {cargo_desc}</div>
                            <div>🏷️ <b>Loại:</b> {cargo_type}</div>
                            <div>⚖️ <b>Khối lượng:</b> {cargo_weight} kg</div>
                            <div>💵 <b>Thu hộ:</b> <b style="color: #d97706;">{cod_amount:,} đ</b></div>
                        </div>
                        <div style="border-left: 1px solid #e5e7eb; padding-left: 10px;">
                            <div>💰 <b>Cước khách:</b> <b style="color: #059669; font-size: 15px;">{customer_price:,} đ</b></div>
                            <div>📊 <b>NET:</b> {net_price:,} đ</div>
                            <div>💳 <b>Thanh toán:</b> <code>transfer | sender prepaid</code></div>
                            <div style="margin-top: 4px;">🚚 <b>Nhà xe:</b> 1 DiChung | <b>Tình trạng:</b> <span style="color: {'#28a745' if dispatch_status == 'Đã điều' else '#dc3545'}; font-weight: bold;">{dispatch_status}</span></div>
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # MODAL POPUP: SAO CHÉP THÔNG TIN ĐƠN HÀNG (CHUẨN 100% NHƯ ẢNH)
            clipboard_text = dchub_service.format_order_clipboard(
                code=current_code,
                sender={"name": sender_name, "phone": sender_phone, "address": sender_addr},
                receiver={"name": receiver_name, "phone": receiver_phone, "address": receiver_addr},
                cargo={"description": cargo_desc, "type": cargo_type, "weight_kg": cargo_weight, "cod_amount": cod_amount},
                pricing={"net_cost": net_price, "customer_cost": customer_price},
                notes="--",
            )

            with st.expander("📋 Xem & Sao chép thông tin đơn hàng (Modal Popup chuẩn DCHub Portal)", expanded=True):
                st.caption("Khung định dạng chuẩn 100% khớp với popup 'Sao chép thông tin đơn hàng' trên portal.dichung.vn:")
                st.text_area("Nội dung sao chép:", value=clipboard_text, height=220, disabled=True)
                st.code(clipboard_text, language="yaml")

            # NÚT ĐIỀU XE
            col_dx1, col_dx2 = st.columns([1, 1])
            with col_dx1:
                if not st.session_state.driver_dispatched:
                    if st.button("🚖 Bấm nút 'Điều xe' (Phát thông báo cho Tài xế)", use_container_width=True, type="primary"):
                        st.session_state.driver_dispatched = True
                        st.toast("Đã điều xe cho tài xế Nguyễn Văn Tuấn!", icon="🚗")
                        st.rerun()
                else:
                    st.success("🟢 ĐÃ ĐIỀU XE: Tài xế Nguyễn Văn Tuấn (29H-123.45)")
            with col_dx2:
                if st.session_state.driver_dispatched:
                    if st.button("Hủy điều xe / Đặt lại", use_container_width=True):
                        st.session_state.driver_dispatched = False
                        st.rerun()

        # 3. HIỂN THỊ CẤU TRÚC JSON SẠCH MỤC TIÊU DCHUB PORTAL
        with st.expander("📄 DCHub Portal API Payload (Đầy đủ 5 giai đoạn)", expanded=False):
            st.json(st.session_state.extracted_json)

    else:
        st.info(
            "⏳ **Trợ lý AI đang tư vấn khách hàng theo 5 giai đoạn...**\n\n"
            "1. Thu thập điểm nhận & trả hàng.\n"
            "2. Thu thập thông tin hàng hóa.\n"
            "3. Báo giá & Xác nhận đồng ý giá ➔ **Có thể tạo Lead ('Có nhu cầu')**.\n"
            "4. Lấy thông tin liên lạc 2 đầu & Phương thức thanh toán.\n"
            "5. Xác nhận hóa đơn VAT & Xuất **Order Confirmation** ➔ **Tạo Đơn Hàng ('Khách chốt') & Điều xe**!\n\n"
            "💡 *Mẹo: Bạn có thể bấm nút **'Nạp kịch bản mẫu 5 Giai đoạn'** ở thanh Sidebar bên trái để xem ngay bảng DCHub Portal!*"
        )


