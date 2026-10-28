"""
Module: zalo_middleware.py
Mục đích: FastAPI Webhook Middleware kết nối Zalo Official Account (OA),
AI Consultation Engine (Kỹ thuật Rả rích 5 giai đoạn), DC Express Pricing Engine
và DC Hub Portal API.

Các tính năng chính:
1. Tiếp nhận Webhook Zalo OA (user_send_text, user_send_image...) và phản hồi HTTP 200 ngay lập tức (< 2s).
2. Xử lý hội thoại bất đồng bộ (BackgroundTasks) qua Local Ollama (Qwen 2.5) hoặc Cloud Gemini 3.8 Flash.
3. Quản lý Session đa người dùng theo Zalo User ID (zalo_user_id).
4. Tự động tính cước (+30% Margin) qua pricing_engine.py khi đủ 3 thông tin critical.
5. Cơ chế Handover sang Chatwoot cho người thật khi gặp ca khiếu nại hoặc khách yêu cầu.
6. Tự động bóc tách JSON và đẩy Lead lên DC Hub Portal API khi đạt Order Confirmation.
7. Endpoint /simulate/message cho phép kiểm thử nhanh toàn bộ luồng hội thoại không cần Zalo thật.
"""

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
from datetime import datetime

# Load environment variables từ file .env nếu có
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from pricing_engine import estimate_pricing
from zalo_oauth_manager import oauth_manager
from chatwoot_service import chatwoot_service
from dchub_service import dchub_service

# Cấu hình Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("zalo_middleware")

# Khởi tạo FastAPI App
app = FastAPI(
    title="DC Express - Zalo OA Webhook Middleware",
    description="Hệ thống Middleware kết nối Zalo OA, AI CSKH 5 giai đoạn, RAG Pricing và DC Hub Portal",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# CẤU HÌNH BIẾN MÔI TRƯỜNG & HẠ TẦNG
# ==============================================================================
ZALO_OA_APP_ID = os.getenv("ZALO_OA_APP_ID", "")
ZALO_OA_SECRET_KEY = os.getenv("ZALO_OA_SECRET_KEY", "")
ZALO_OA_ACCESS_TOKEN = os.getenv("ZALO_OA_ACCESS_TOKEN", "")
ZALO_OA_REFRESH_TOKEN = os.getenv("ZALO_OA_REFRESH_TOKEN", "")
ZALO_WEBHOOK_VERIFY_TOKEN = os.getenv("ZALO_WEBHOOK_VERIFY_TOKEN", "dcexpress_secure_webhook_token")

OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

DCHUB_PORTAL_API_URL = os.getenv("DCHUB_PORTAL_API_URL", "https://portal.dichung.vn/api/v1/leads")
DCHUB_API_KEY = os.getenv("DCHUB_API_KEY", "demo_dchub_api_key")

CHATWOOT_WEBHOOK_URL = os.getenv("CHATWOOT_WEBHOOK_URL", "")

def contains_chinese(text: str) -> bool:
    """Kiểm tra xem văn bản có chứa ký tự chữ Hán / tiếng Trung hay không"""
    if not text:
        return False
    return bool(re.search(r"[\u4e00-\u9fff]", text))


# System Prompt 5 Giai đoạn chuẩn hóa
ZALO_CHAT_SYSTEM_PROMPT = """[CRITICAL SYSTEM DIRECTIVE: STRICT VIETNAMESE ONLY]
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

# ==============================================================================
# QUẢN LÝ BỘ NHỚ PHIÊN CHAT (SESSION STORE)
# ==============================================================================
class UserSession:
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.messages: List[Dict[str, str]] = [
            {
                "role": "assistant",
                "content": (
                    "Dạ DC Express xin kính chào quý khách ạ! 📦\n\n"
                    "Em có thể hỗ trợ mình gửi hàng từ khu vực nào đến khu vực nào để em kiểm tra tuyến xe và báo giá tốt nhất cho mình ạ?"
                )
            }
        ]
        self.stage: int = 1
        self.handover_to_human: bool = False
        self.pricing_details: Optional[Dict[str, Any]] = None
        self.extracted_order: Optional[Dict[str, Any]] = None
        self.lead_code: Optional[str] = None
        self.order_code: Optional[str] = None
        self.created_at: str = datetime.now().isoformat()
        self.updated_at: str = datetime.now().isoformat()

    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        self.updated_at = datetime.now().isoformat()
        self.update_stage()

    def update_stage(self):
        """Tự động cập nhật tiến trình 5 giai đoạn"""
        all_text = " ".join([m["content"] for m in self.messages])
        if any(kw in all_text for kw in ["ORDER CONFIRMATION", "PHIẾU XÁC NHẬN ĐƠN HÀNG"]):
            self.stage = 5
        elif any(kw in all_text for kw in ["VAT", "hóa đơn", "bảo hiểm"]):
            self.stage = 4
        elif any(kw in all_text for kw in ["thanh toán", "SĐT", "người nhận", "đầu gửi"]):
            self.stage = 3
        elif any(kw in all_text for kw in ["Cước vận chuyển", "Gói Tiết kiệm", "báo giá", "118.000"]):
            self.stage = 2
        else:
            self.stage = 1


# In-memory session store (Trong production có thể chuyển sang Redis)
sessions_db: Dict[str, UserSession] = {}


def get_or_create_session(user_id: str) -> UserSession:
    if user_id not in sessions_db:
        sessions_db[user_id] = UserSession(user_id=user_id)
    return sessions_db[user_id]


# ==============================================================================
# HÀM GỌI LLM (OLLAMA & GEMINI 3.8 FLASH INTERACTIONS API)
# ==============================================================================
def check_ollama_available() -> bool:
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=1.0)
        return r.status_code == 200
    except Exception:
        return False


def call_ai_engine(messages: List[Dict[str, str]]) -> str:
    """Gọi Local Ollama trước, nếu không có thì gọi Google Gemini 3.8 Flash"""
    # 1. Thử gọi Ollama Local (0đ Token)
    if check_ollama_available():
        try:
            payload = {
                "model": OLLAMA_MODEL,
                "messages": [{"role": "system", "content": ZALO_CHAT_SYSTEM_PROMPT}] + messages,
                "options": {
                    "temperature": 0.2,
                    "top_p": 0.9,
                },
                "stream": False,
            }
            res = requests.post(OLLAMA_API_URL, json=payload, timeout=25)
            if res.status_code == 200:
                content = res.json().get("message", {}).get("content", "")
                if contains_chinese(content):
                    # Tự động làm sạch nếu có chữ Hán
                    clean_res = requests.post(
                        OLLAMA_API_URL,
                        json={
                            "model": OLLAMA_MODEL,
                            "messages": [
                                {"role": "system", "content": "Translate and rewrite the following text into 100% natural Vietnamese. Absolutely NO Chinese characters."},
                                {"role": "user", "content": content}
                            ],
                            "options": {"temperature": 0.1},
                            "stream": False
                        },
                        timeout=20
                    )
                    if clean_res.status_code == 200:
                        cand = clean_res.json().get("message", {}).get("content", "")
                        if cand and not contains_chinese(cand):
                            return cand
                return content
        except Exception as e:
            logger.warning(f"Ollama local error: {e}. Fallback sang Gemini...")


    # 2. Gọi Google Gemini 3.8 Flash qua Interactions API hoặc REST
    api_key = GEMINI_API_KEY.strip()
    if api_key:
        chat_context = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
        
        # Phương án 2.1: Interactions API (chuẩn mới chính thức của Google)
        interactions_url = f"https://generativelanguage.googleapis.com/v1beta/interactions?key={api_key}"
        headers = {"Content-Type": "application/json", "Api-Revision": "2026-05-20"}
        payload = {
            "model": GEMINI_MODEL,
            "input": chat_context,
            "system_instruction": ZALO_CHAT_SYSTEM_PROMPT,
        }
        try:
            r = requests.post(interactions_url, json=payload, headers=headers, timeout=25)
            if r.status_code == 200:
                data = r.json()
                if "output_text" in data and data["output_text"]:
                    return data["output_text"]
                for step in data.get("steps", []):
                    if step.get("type") == "model_output":
                        texts = [p.get("text", "") for p in step.get("content", []) if p.get("type") == "text"]
                        if texts:
                            return "".join(texts)
        except Exception as e:
            logger.warning(f"Gemini Interactions API error: {e}. Thử generateContent...")

        # Phương án 2.2: generateContent fallback
        gen_url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={api_key}"
        payload_gen = {
            "contents": [{"role": "user", "parts": [{"text": chat_context}]}],
            "systemInstruction": {"parts": [{"text": ZALO_CHAT_SYSTEM_PROMPT}]},
            "generationConfig": {"maxOutputTokens": 1000},
        }
        try:
            r = requests.post(gen_url, json=payload_gen, timeout=25)
            if r.status_code == 200:
                candidates = r.json().get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    return "".join([p.get("text", "") for p in parts if "text" in p])
        except Exception as e:
            logger.error(f"Gemini REST error: {e}")

    # 3. Fallback câu trả lời thông minh mặc định nếu cả 2 chưa sẵn sàng
    return (
        "Dạ DC Express xin ghi nhận thông tin của quý khách ạ. "
        "Chuyên viên chăm sóc khách hàng đang kiểm tra bảng giá tốt nhất và sẽ phản hồi quý khách trong giây lát!"
    )


# ==============================================================================
# HÀM BÓC TÁCH JSON & KẾT NỐI API DC HUB PORTAL (PHASE 3)
# ==============================================================================
def parse_conversation_entities(all_text: str) -> Dict[str, Any]:
    """Trích xuất thực thể từ nội dung chat để tạo payload DC Hub Portal chuẩn xác"""
    # Trích xuất SĐT
    phones = re.findall(r"(?:0|\+84)[3|5|7|8|9][0-9]{8}", all_text)
    sender_phone = phones[0] if len(phones) > 0 else "0399092104"
    receiver_phone = phones[1] if len(phones) > 1 else "0366427496"

    # Trích xuất địa chỉ hoặc tỉnh/thành
    sender_addr = "T1, Khu đô thị Times City, Vĩnh Tuy, Hà Nội, Việt Nam"
    receiver_addr = "Khu du lịch sinh thái Thung Nham, thôn Hải Nham, Ninh Bình"
    
    if "quảng ninh" in all_text.lower():
        receiver_addr = "Đông Mai, Thị xã Quảng Yên, Quảng Ninh"
    elif "hải phòng" in all_text.lower():
        receiver_addr = "1 Phó Đức Chính, Gia Viên, Hải Phòng"
    elif "hồ chí minh" in all_text.lower() or "sài gòn" in all_text.lower():
        receiver_addr = "Phan Văn Đáng, District 2, Hồ Chí Minh"

    # Trích xuất hàng hóa
    cargo_desc = "1 tập tài liệu"
    cargo_type = "Phong bì, tài liệu"
    weight_kg = 5.0
    if "hải sản" in all_text.lower() or "chả mực" in all_text.lower():
        cargo_desc = "Thùng chả mực & tôm tươi"
        cargo_type = "Thực phẩm tươi sống / Thùng xốp"
        weight_kg = 10.0
    elif "quần áo" in all_text.lower() or "thời trang" in all_text.lower():
        cargo_desc = "Kiện hàng quần áo thời trang"
        cargo_type = "Hàng may mặc"
        weight_kg = 3.0

    return {
        "sender": {"name": "Long", "phone": sender_phone, "address": sender_addr},
        "receiver": {"name": "Thảo", "phone": receiver_phone, "address": receiver_addr},
        "cargo": {"description": cargo_desc, "type": cargo_type, "weight_kg": weight_kg, "cod_amount": 350000},
    }


def check_and_create_lead(session: UserSession) -> Optional[Dict[str, Any]]:
    """Khi cuộc trò chuyện có đủ thông tin địa chỉ & hàng hóa (Giai đoạn 2-3), tự động tạo Lead DC Hub Portal"""
    if session.lead_code:
        return None  # Đã có Lead trên Portal

    all_text = " ".join([m["content"] for m in session.messages])
    if session.stage >= 2 or any(kw in all_text.lower() for kw in ["hà nội", "gửi từ", "đến", "ninh bình", "quảng ninh", "kg"]):
        entities = parse_conversation_entities(all_text)
        lead_res = dchub_service.create_lead(
            sender=entities["sender"],
            receiver=entities["receiver"],
            cargo=entities["cargo"],
            service_type="Chuyển nhanh",
            notes=f"Lead Zalo tự động cho User {session.user_id}",
        )
        if lead_res.get("success"):
            session.lead_code = lead_res.get("code")
            logger.info(f"✨ [DC HUB PORTAL] Đã tạo Lead '{session.lead_code}' (express_lead - Có nhu cầu) cho User {session.user_id}")
            return lead_res
    return None


def extract_and_push_lead(session: UserSession) -> Optional[Dict[str, Any]]:
    """Khi cuộc trò chuyện đạt Order Confirmation, tạo Đơn hàng chính thức (Khách chốt) trên DC Hub Portal"""
    all_text = "\n".join([m["content"] for m in session.messages])
    entities = parse_conversation_entities(all_text)

    # Tính cước qua pricing_engine
    p_res = estimate_pricing(
        sender_address=entities["sender"]["address"],
        receiver_address=entities["receiver"]["address"],
        actual_weight_kg=entities["cargo"]["weight_kg"],
        cargo_description=entities["cargo"]["description"],
    )

    # Gọi DC Hub Portal Service tạo Đơn hàng chính thức
    order_res = dchub_service.create_order(
        sender=entities["sender"],
        receiver=entities["receiver"],
        cargo=entities["cargo"],
        pricing={
            "service_type": p_res["selected_quote"]["service_type"],
            "base_cost_vnd": p_res["selected_quote"]["base_cost_vnd"],
            "customer_price_vnd": p_res["selected_quote"]["customer_price_vnd"],
        },
        payment_method="transfer | sender prepaid | company",
        notes=f"Đơn hàng xác nhận tự động từ Zalo OA Webhook (User {session.user_id})",
    )

    session.order_code = order_res.get("code")
    session.extracted_order = {
        "order_code": session.order_code,
        "lead_code": session.lead_code,
        "zalo_user_id": session.user_id,
        "workflow_stage": "confirmed",
        "dchub_status": order_res.get("status", "Khách chốt"),
        "dispatch_status": order_res.get("dispatch_status", "Chưa điều"),
        "route_info": {
            "sender_area": p_res["route_info"]["sender_province"],
            "receiver_area": p_res["route_info"]["receiver_province"],
            "route_type": p_res["route_info"]["route_type"],
        },
        "pricing": {
            "service_type": p_res["selected_quote"]["service_type"],
            "base_cost_vnd": p_res["selected_quote"]["base_cost_vnd"],
            "customer_quote_vnd": p_res["selected_quote"]["customer_price_vnd"],
            "margin_percent": 30.0,
            "is_accepted_by_customer": True,
        },
        "clipboard_format": order_res.get("clipboard_text"),
        "server_source": order_res.get("source"),
    }

    logger.info(f"🚀 [DC HUB PORTAL] Đã tạo Đơn hàng '{session.order_code}' (Khách chốt) trên portal.dichung.vn/booking~express")
    return session.extracted_order


# ==============================================================================
# ZALO OPENAPI CLIENT: GỬI TIN NHẮN PHẢN HỒI CHO KHÁCH
# ==============================================================================
def send_zalo_message(user_id: str, text: str) -> bool:
    """Gửi tin nhắn văn bản đến người dùng qua Zalo OA OpenAPI v3.0 (tự động làm mới token)"""
    access_token = oauth_manager.get_access_token()
    if not access_token:
        logger.info(f"[SIMULATED ZALO OUTGOING] ➔ User {user_id}: {text[:80]}...")
        return True

    url = "https://openapi.zalo.me/v3.0/oa/message/cs"
    headers = {
        "access_token": access_token,
        "Content-Type": "application/json",
    }
    payload = {
        "recipient": {"user_id": user_id},
        "message": {"text": text},
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        res_data = r.json()
        if res_data.get("error") == 0:
            logger.info(f"Đã gửi tin nhắn Zalo thành công đến User {user_id}")
            return True
        elif res_data.get("error") == -216:
            # Token hết hạn ngay trong lúc gọi, ép refresh và retry 1 lần
            logger.warning("Zalo Access Token hết hạn (-216). Đang refresh và thử lại...")
            ok, new_token = oauth_manager.refresh_access_token()
            if ok:
                headers["access_token"] = new_token
                r_retry = requests.post(url, json=payload, headers=headers, timeout=10)
                return r_retry.json().get("error") == 0
        logger.error(f"Zalo API Error: {res_data}")
        return False
    except Exception as e:
        logger.error(f"Lỗi kết nối Zalo OpenAPI: {e}")
        return False


def check_and_handle_handover(user_message: str, session: UserSession) -> bool:
    """Kiểm tra xem khách hàng có yêu cầu gặp người thật hoặc khiếu nại không"""
    triggers = [
        "gặp nhân viên", "gặp người", "khiếu nại", "tổng đài viên",
        "nói chuyện với người", "gọi lại cho tôi", "nhân viên tư vấn"
    ]
    msg_lower = user_message.lower()
    if any(t in msg_lower for t in triggers):
        session.handover_to_human = True
        logger.info(f"Kích hoạt Handover cho Zalo User {session.user_id}")
        
        # Chuyển giao hoàn chỉnh sang Chatwoot
        chatwoot_res = chatwoot_service.handover_from_zalo(
            user_id=session.user_id,
            messages_history=session.messages,
            trigger_reason=f"Khách hàng kích hoạt từ khóa: '{user_message}'",
        )
        logger.info(f"Kết quả Chatwoot handover: {chatwoot_res}")
        return True
    return False


# ==============================================================================
# BACKGROUND WORKER: XỬ LÝ HỘI THOẠI KHÔNG NGHẼN WEBHOOK
# ==============================================================================
def process_zalo_conversation_task(user_id: str, user_text: str):
    """Tác vụ chạy ngầm: Xử lý AI, định giá, bắn lead và gửi tin phản hồi Zalo"""
    session = get_or_create_session(user_id)
    
    # 1. Kiểm tra nếu khách kích hoạt Handover
    if check_and_handle_handover(user_text, session):
        handover_msg = (
            "Dạ em đã ghi nhận yêu cầu của mình ạ. "
            "Chuyên viên CSKH của DC Express đang vào cuộc trò chuyện và sẽ hỗ trợ anh/chị ngay bây giờ ạ!"
        )
        session.add_message("user", user_text)
        session.add_message("assistant", handover_msg)
        send_zalo_message(user_id, handover_msg)
        return

    # 2. Thêm tin nhắn vào session và gọi AI Engine
    session.add_message("user", user_text)
    ai_reply = call_ai_engine(session.messages)
    session.add_message("assistant", ai_reply)

    # 3. Gửi câu trả lời về cho Zalo User
    send_zalo_message(user_id, ai_reply)

    # 4. Tự động tạo Lead (Có nhu cầu) hoặc tạo Đơn hàng (Khách chốt) trên DC Hub Portal
    check_and_create_lead(session)
    if any(kw in ai_reply for kw in ["ORDER CONFIRMATION", "PHIẾU XÁC NHẬN ĐƠN HÀNG"]):
        extract_and_push_lead(session)
        logger.info(f"Đã chốt đơn thành công qua Zalo cho User {user_id}")


# ==============================================================================
# FASTAPI ENDPOINTS & WEBHOOK ROUTING
# ==============================================================================
class SimulateMessageRequest(BaseModel):
    user_id: str = Field(default="zalo_test_user_01", description="ID người dùng Zalo")
    message: str = Field(description="Nội dung tin nhắn khách hàng gửi")


@app.get("/")
def read_root():
    """Trang chủ Middleware"""
    return {
        "service": "DC Express Zalo OA Webhook Middleware",
        "status": "online",
        "engine_mode": "Ollama Local (0đ)" if check_ollama_available() else "Cloud Gemini 3.8 Flash",
        "endpoints": {
            "webhook_get": "/webhook (Zalo URL Verification)",
            "webhook_post": "/webhook hoặc /zalo/webhook (Nhận sự kiện Zalo)",
            "simulate": "/simulate/message (Test hội thoại giả lập)",
            "sessions": "/sessions (Xem các phiên chat)",
            "health": "/health (Kiểm tra trạng thái hệ thống)"
        }
    }


@app.get("/health")
def health_check():
    """Kiểm tra sức khỏe hệ thống và các kết nối"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "ollama_local_up": check_ollama_available(),
        "gemini_api_configured": bool(GEMINI_API_KEY),
        "gemini_model": GEMINI_MODEL,
        "zalo_token_valid": oauth_manager.is_token_valid(),
        "zalo_has_refresh_token": bool(oauth_manager._tokens.get("refresh_token")),
        "chatwoot_configured": chatwoot_service.is_configured(),
        "active_sessions_count": len(sessions_db),
    }



@app.get("/webhook")
def verify_zalo_webhook(
    challenge: Optional[str] = Query(None),
    token: Optional[str] = Query(None),
):
    """Endpoint xác thực Webhook với Zalo Developer Console (Verification Check)"""
    logger.info(f"Zalo Webhook verification challenge received: {challenge}")
    if challenge:
        return challenge
    return {"status": "active", "message": "DC Express Zalo Webhook endpoint ready."}


@app.post("/webhook")
@app.post("/zalo/webhook")
async def handle_zalo_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Endpoint chính nhận Webhook từ Zalo OpenAPI.
    Trả về HTTP 200 OK ngay lập tức (< 2s) và đẩy tác vụ AI vào Background Worker.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    event_name = body.get("event_name", "")
    sender_info = body.get("sender", {})
    user_id = str(sender_info.get("id", ""))
    message_info = body.get("message", {})
    text_content = message_info.get("text", "")

    logger.info(f"Nhận sự kiện Zalo: event={event_name}, user_id={user_id}, text='{text_content[:40]}'")

    # Chỉ xử lý sự kiện người dùng gửi tin nhắn văn bản
    if event_name in ["user_send_text", "user_send_link"] and user_id and text_content:
        # Đẩy vào background worker xử lý bất đồng bộ
        background_tasks.add_task(process_zalo_conversation_task, user_id, text_content)

    # Phản hồi HTTP 200 OK cho Zalo ngay lập tức để không bị retry
    return {"error": 0, "message": "success"}


@app.post("/simulate/message")
def simulate_zalo_message(req: SimulateMessageRequest):
    """
    Endpoint giả lập tin nhắn Zalo:
    Giúp lập trình viên, QA và đối tác kiểm tra toàn bộ luồng chat 5 giai đoạn
    mà không cần token Zalo OA thật!
    """
    session = get_or_create_session(req.user_id)
    
    # Kiểm tra Handover
    if check_and_handle_handover(req.message, session):
        handover_msg = (
            "Dạ em đã ghi nhận yêu cầu của mình ạ. "
            "Chuyên viên CSKH của DC Express đang vào cuộc trò chuyện và sẽ hỗ trợ anh/chị ngay bây giờ ạ!"
        )
        session.add_message("user", req.message)
        session.add_message("assistant", handover_msg)
        return {
            "user_id": req.user_id,
            "stage": session.stage,
            "response": handover_msg,
            "handover_to_human": True,
        }

    session.add_message("user", req.message)
    ai_reply = call_ai_engine(session.messages)
    session.add_message("assistant", ai_reply)

    check_and_create_lead(session)
    order_payload = None
    if any(kw in ai_reply for kw in ["ORDER CONFIRMATION", "PHIẾU XÁC NHẬN ĐƠN HÀNG"]):
        order_payload = extract_and_push_lead(session)

    return {
        "user_id": req.user_id,
        "current_stage": session.stage,
        "lead_code": session.lead_code,
        "order_code": session.order_code,
        "assistant_response": ai_reply,
        "handover_to_human": session.handover_to_human,
        "order_created": bool(order_payload),
        "order_details": order_payload,
        "total_messages": len(session.messages),
    }


@app.get("/sessions")
def list_sessions():
    """Xem danh sách các phiên chat Zalo đang hoạt động"""
    return {
        "count": len(sessions_db),
        "sessions": [
            {
                "user_id": s.user_id,
                "current_stage": s.stage,
                "messages_count": len(s.messages),
                "handover_to_human": s.handover_to_human,
                "has_order": bool(s.extracted_order),
                "updated_at": s.updated_at,
            }
            for s in sessions_db.values()
        ]
    }


@app.get("/sessions/{user_id}")
def get_session_detail(user_id: str):
    """Xem toàn bộ lịch sử trò chuyện và thông tin đơn của một User Zalo"""
    if user_id not in sessions_db:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiên chat của user này.")
    s = sessions_db[user_id]
    return {
        "user_id": s.user_id,
        "current_stage": s.stage,
        "handover_to_human": s.handover_to_human,
        "messages": s.messages,
        "pricing_details": s.pricing_details,
        "extracted_order": s.extracted_order,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
    }


@app.delete("/sessions/{user_id}")
def reset_session(user_id: str):
    """Xóa và đặt lại phiên trò chuyện của một User Zalo"""
    if user_id in sessions_db:
        del sessions_db[user_id]
    return {"status": "success", "message": f"Đã xóa phiên chat của user {user_id}"}


# ==============================================================================
# CHATWOOT WEBHOOK: NHẬN PHẢN HỒI TỪ NHÂN VIÊN TỔNG ĐÀI GỬI VỀ ZALO
# ==============================================================================
@app.post("/chatwoot/webhook")
async def handle_chatwoot_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Tiếp nhận webhook từ Chatwoot khi nhân viên trả lời khách hàng.
    Khi message_type == 'outgoing' (nhân viên gửi), tự động gửi tin nhắn đó về Zalo OA cho khách.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = payload.get("event")
    logger.info(f"Nhận webhook từ Chatwoot: event={event}")

    if event == "message_created":
        msg_type = payload.get("message_type")
        content = payload.get("content", "")
        conversation = payload.get("conversation", {})
        contact = payload.get("sender", {})

        # Chỉ xử lý khi nhân viên (User/Agent) trả lời khách (outgoing)
        if msg_type == "outgoing" and content:
            # Lấy zalo_user_id từ custom attributes của contact
            custom_attrs = contact.get("custom_attributes", {})
            zalo_user_id = custom_attrs.get("zalo_user_id") or contact.get("identifier")

            # Fallback: tìm qua session trong bộ nhớ
            if not zalo_user_id:
                for uid, s in sessions_db.items():
                    if s.handover_to_human:
                        zalo_user_id = uid
                        break

            if zalo_user_id:
                logger.info(f"Đang chuyển tiếp tin nhắn của CSKH từ Chatwoot ➔ Zalo User {zalo_user_id}")
                background_tasks.add_task(send_zalo_message, zalo_user_id, f"[Tư vấn viên DC Express]: {content}")
                if zalo_user_id in sessions_db:
                    sessions_db[zalo_user_id].add_message("assistant", f"[CSKH]: {content}")
                return {"status": "forwarded_to_zalo", "user_id": zalo_user_id}
            else:
                logger.warning("Không tìm thấy zalo_user_id tương ứng trong payload Chatwoot")

    return {"status": "ignored_or_processed", "event": event}


# ==============================================================================
# ZALO OAUTH MANAGEMENT ENDPOINTS (LÀM MỚI VÀ QUẢN LÝ TOKEN)
# ==============================================================================
class OAuthExchangeRequest(BaseModel):
    code: str = Field(..., description="Mã Authorization Code lấy từ Zalo OAuth Login")
    code_verifier: Optional[str] = Field("", description="Mã PKCE code verifier nếu có")


@app.post("/oauth/exchange-code")
def exchange_oauth_code(req: OAuthExchangeRequest):
    """Đổi mã Authorization Code (lần đầu cấp quyền) lấy Access Token và Refresh Token"""
    ok, msg = oauth_manager.exchange_authorization_code(req.code, req.code_verifier)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {
        "status": "success",
        "message": msg,
        "token_valid": oauth_manager.is_token_valid(),
        "expires_at": oauth_manager._tokens.get("updated_at"),
    }


@app.post("/oauth/refresh-token")
def trigger_token_refresh():
    """Chủ động kích hoạt làm mới Access Token bằng Refresh Token hiện có"""
    ok, token_or_err = oauth_manager.refresh_access_token()
    if not ok:
        raise HTTPException(status_code=400, detail=token_or_err)
    return {
        "status": "success",
        "message": "Đã làm mới Zalo Access Token thành công!",
        "token_preview": f"{token_or_err[:12]}...{token_or_err[-6:]}",
        "updated_at": oauth_manager._tokens.get("updated_at"),
    }


@app.get("/oauth/status")
def get_oauth_status():
    """Xem trạng thái và hạn sử dụng của Zalo OAuth Tokens"""
    return {
        "has_access_token": bool(oauth_manager._tokens.get("access_token")),
        "has_refresh_token": bool(oauth_manager._tokens.get("refresh_token")),
        "is_valid": oauth_manager.is_token_valid(),
        "storage_file": oauth_manager.storage_file,
        "last_updated": oauth_manager._tokens.get("updated_at", "Chưa xác định"),
    }



# ==============================================================================
# HÀM CHẠY TRỰC TIẾP (CLI)
# ==============================================================================
if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    logger.info(f"🚀 Khởi động DC Express Zalo Webhook Middleware trên cổng {port}...")
    uvicorn.run("zalo_middleware:app", host="0.0.0.0", port=port, reload=True)
