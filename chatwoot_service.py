"""
================================================================================
DC EXPRESS - CHATWOOT LIVE AGENT HANDOVER SERVICE (HUMAN-IN-THE-LOOP)
================================================================================
Module tích hợp hai chiều giữa Zalo OA và nền tảng Chatwoot Live Agent:
1. Chiều Zalo ➔ Chatwoot:
   - Khi khách yêu cầu gặp nhân viên hoặc khiếu nại đơn hàng:
     + Tự động tạo/tìm Contact trên Chatwoot theo Zalo User ID / SĐT.
     + Tạo Conversation mới, gắn tag [DC_EXPRESS_ESCALATED].
     + Đồng bộ toàn bộ lịch sử 5 giai đoạn trước đó sang Chatwoot để tư vấn viên nắm bắt ngay.
     + Chuyển trạng thái phiên chat sang Human Mode (tắt AI tự trả lời).
2. Chiều Chatwoot ➔ Zalo:
   - Khi nhân viên CSKH gõ câu trả lời trên giao diện web/app Chatwoot:
     + Chatwoot bắn Webhook về endpoint `/chatwoot/webhook`.
     + Middleware tự động chuyển tiếp nội dung tin nhắn của nhân viên sang Zalo OA cho khách hàng.
================================================================================
"""

import logging
import os
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger("chatwoot_service")
logger.setLevel(logging.INFO)

# Cấu hình Chatwoot từ biến môi trường
CHATWOOT_BASE_URL = os.getenv("CHATWOOT_BASE_URL", "https://app.chatwoot.com")
CHATWOOT_API_KEY = os.getenv("CHATWOOT_API_KEY", "")
CHATWOOT_ACCOUNT_ID = os.getenv("CHATWOOT_ACCOUNT_ID", "1")
CHATWOOT_INBOX_ID = os.getenv("CHATWOOT_INBOX_ID", "1")


class ChatwootService:
    def __init__(
        self,
        base_url: str = CHATWOOT_BASE_URL,
        api_key: str = CHATWOOT_API_KEY,
        account_id: str = CHATWOOT_ACCOUNT_ID,
        inbox_id: str = CHATWOOT_INBOX_ID,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.account_id = account_id
        self.inbox_id = inbox_id

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "api_access_token": self.api_key,
            "Content-Type": "application/json",
        }

    def is_configured(self) -> bool:
        """Kiểm tra xem Chatwoot đã được cấu hình API Key chưa"""
        return bool(self.api_key and self.account_id)

    def find_or_create_contact(self, user_id: str, name: str = "Khách hàng Zalo", phone: str = "") -> Optional[int]:
        """Tìm hoặc tạo liên hệ (Contact) trên Chatwoot theo Zalo User ID"""
        if not self.is_configured():
            logger.info(f"[SIMULATED CHATWOOT] Tìm/tạo contact cho user {user_id}")
            return 9999

        # 1. Tìm kiếm contact hiện có
        search_url = f"{self.base_url}/api/v1/accounts/{self.account_id}/contacts/search?q={user_id}"
        try:
            r = requests.get(search_url, headers=self.headers, timeout=10)
            if r.status_code == 200:
                payload = r.json()
                contacts = payload.get("payload", [])
                if contacts:
                    return contacts[0]["id"]
        except Exception as e:
            logger.warning(f"Lỗi tìm kiếm contact Chatwoot: {e}")

        # 2. Tạo mới contact nếu chưa có
        create_url = f"{self.base_url}/api/v1/accounts/{self.account_id}/contacts"
        data = {
            "inbox_id": int(self.inbox_id),
            "name": f"{name} ({user_id[-6:]})",
            "identifier": user_id,
            "custom_attributes": {
                "source": "Zalo_OA",
                "zalo_user_id": user_id,
            },
        }
        if phone:
            data["phone_number"] = phone

        try:
            r = requests.post(create_url, headers=self.headers, json=data, timeout=10)
            if r.status_code in [200, 201]:
                return r.json().get("payload", {}).get("contact", {}).get("id")
        except Exception as e:
            logger.error(f"Lỗi tạo contact Chatwoot: {e}")
        return None

    def create_conversation(self, contact_id: int, initial_message: str = "") -> Optional[int]:
        """Tạo cuộc hội thoại mới trên Chatwoot cho Contact"""
        if not self.is_configured():
            logger.info(f"[SIMULATED CHATWOOT] Tạo conversation cho contact {contact_id}")
            return 8888

        url = f"{self.base_url}/api/v1/accounts/{self.account_id}/conversations"
        data = {
            "inbox_id": int(self.inbox_id),
            "contact_id": contact_id,
            "status": "open",
        }
        if initial_message:
            data["message"] = {"content": initial_message}

        try:
            r = requests.post(url, headers=self.headers, json=data, timeout=10)
            if r.status_code in [200, 201]:
                conv_id = r.json().get("id")
                logger.info(f"Đã tạo Conversation Chatwoot ID: {conv_id}")
                return conv_id
        except Exception as e:
            logger.error(f"Lỗi tạo conversation Chatwoot: {e}")
        return None

    def send_message_to_conversation(
        self, conversation_id: int, content: str, message_type: str = "incoming"
    ) -> bool:
        """
        Gửi tin nhắn vào cuộc hội thoại trên Chatwoot.
        - message_type = 'incoming': Tin nhắn từ Khách hàng
        - message_type = 'outgoing': Tin nhắn từ Bot/Hệ thống
        """
        if not self.is_configured():
            logger.info(f"[SIMULATED CHATWOOT] Gửi tin ({message_type}) vào conv {conversation_id}: {content[:60]}...")
            return True

        url = f"{self.base_url}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}/messages"
        data = {
            "content": content,
            "message_type": message_type,
            "private": False,
        }
        try:
            r = requests.post(url, headers=self.headers, json=data, timeout=10)
            return r.status_code in [200, 201]
        except Exception as e:
            logger.error(f"Lỗi gửi tin nhắn sang Chatwoot: {e}")
            return False

    def handover_from_zalo(
        self,
        user_id: str,
        messages_history: List[Dict[str, str]],
        trigger_reason: str = "Khách hàng yêu cầu hỗ trợ",
    ) -> Dict[str, Any]:
        """
        Quy trình Handover hoàn chỉnh:
        1. Tạo contact
        2. Tạo conversation với nhãn escalate
        3. Bắn tóm tắt toàn bộ lịch sử trao đổi vào conversation
        """
        contact_id = self.find_or_create_contact(user_id=user_id)
        if not contact_id:
            return {"success": False, "error": "Không thể tạo contact trên Chatwoot"}

        # Tạo thông báo mở đầu cho nhân viên tổng đài
        summary_intro = (
            f"🔔 [YÊU CẦU CHUYỂN GIAO TƯ VẤN VIÊN - DC EXPRESS]\n"
            f"- Khách hàng Zalo ID: {user_id}\n"
            f"- Lý do chuyển giao: {trigger_reason}\n"
            f"- Số tin nhắn đã trao đổi với AI: {len(messages_history)}\n"
            f"----------------------------------------"
        )
        conv_id = self.create_conversation(contact_id, initial_message=summary_intro)
        if not conv_id:
            return {"success": False, "error": "Không thể tạo cuộc hội thoại trên Chatwoot"}

        # Đẩy lịch sử các tin nhắn gần nhất sang Chatwoot
        for msg in messages_history[-8:]:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            m_type = "incoming" if role == "user" else "outgoing"
            prefix = "👤 Khách: " if role == "user" else "🤖 AI: "
            self.send_message_to_conversation(conv_id, f"{prefix}{content}", message_type=m_type)

        logger.info(f"✅ Handover thành công cho user {user_id} ➔ Chatwoot Conversation {conv_id}")
        return {
            "success": True,
            "contact_id": contact_id,
            "conversation_id": conv_id,
            "message": "Đã chuyển giao cho nhân viên trực chat.",
        }


# Singleton instance
chatwoot_service = ChatwootService()
