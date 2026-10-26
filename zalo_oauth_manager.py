"""
================================================================================
DC EXPRESS - ZALO OAUTH TOKEN MANAGER (TỰ ĐỘNG LÀM MỚI ACCESS TOKEN)
================================================================================
Cơ chế OAuth 2.0 của Zalo Official Account:
- Access Token: Có hiệu lực trong 25 giờ (90.000 giây).
- Refresh Token: Có hiệu lực trong 3 tháng. MỖI REFRESH TOKEN CHỈ DÙNG ĐƯỢC 1 LẦN.
  Khi gọi API refresh, Zalo sẽ cấp 1 Access Token MỚI và 1 Refresh Token MỚI.
- Module này tự động kiểm tra hạn, tự động gọi API gia hạn trước khi hết hạn 1 giờ
  và lưu token mới vào file bảo mật (.zalo_tokens.json) hoặc biến môi trường.
================================================================================
"""

import json
import logging
import os
import time
from typing import Dict, Optional, Tuple
import requests

logger = logging.getLogger("zalo_oauth")
logger.setLevel(logging.INFO)

TOKEN_STORAGE_FILE = os.getenv("ZALO_TOKEN_FILE", ".zalo_tokens.json")
ZALO_APP_ID = os.getenv("ZALO_APP_ID", "")
ZALO_SECRET_KEY = os.getenv("ZALO_SECRET_KEY", "")
ZALO_OAUTH_TOKEN_URL = "https://oauth.zaloapp.com/v4/oa/access_token"


class ZaloOAuthManager:
    def __init__(
        self,
        app_id: Optional[str] = None,
        secret_key: Optional[str] = None,
        storage_file: str = TOKEN_STORAGE_FILE,
    ):
        self.app_id = app_id or ZALO_APP_ID
        self.secret_key = secret_key or ZALO_SECRET_KEY
        self.storage_file = storage_file
        self._tokens: Dict[str, str] = {}
        self.load_tokens()

    def load_tokens(self) -> Dict[str, str]:
        """Tải token từ file lưu trữ cục bộ nếu có"""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, "r", encoding="utf-8") as f:
                    self._tokens = json.load(f)
                    logger.info("Đã tải thông tin Zalo OAuth tokens từ file lưu trữ.")
                    return self._tokens
            except Exception as e:
                logger.error(f"Lỗi khi đọc file {self.storage_file}: {e}")

        # Fallback từ biến môi trường
        self._tokens = {
            "access_token": os.getenv("ZALO_OA_ACCESS_TOKEN", ""),
            "refresh_token": os.getenv("ZALO_OA_REFRESH_TOKEN", ""),
            "expires_at": os.getenv("ZALO_TOKEN_EXPIRES_AT", "0"),
        }
        return self._tokens

    def save_tokens(self, access_token: str, refresh_token: str, expires_in: int) -> None:
        """Lưu access_token và refresh_token mới an toàn vào file"""
        expires_at = int(time.time()) + expires_in
        self._tokens = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": str(expires_at),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        }
        try:
            with open(self.storage_file, "w", encoding="utf-8") as f:
                json.dump(self._tokens, f, indent=2, ensure_ascii=False)
            logger.info(f"Đã cập nhật Zalo tokens mới vào {self.storage_file} (Hết hạn lúc {self._tokens['updated_at']})")
        except Exception as e:
            logger.error(f"Lỗi khi ghi file {self.storage_file}: {e}")

    def is_token_valid(self, buffer_seconds: int = 3600) -> bool:
        """Kiểm tra token còn hạn hay không (mặc định buffer trước 1 giờ)"""
        access_token = self._tokens.get("access_token", "")
        expires_at = int(self._tokens.get("expires_at", 0))
        if not access_token:
            return False
        # Nếu thời gian hiện tại + buffer vượt quá expires_at -> cần renew
        if time.time() + buffer_seconds >= expires_at:
            return False
        return True

    def exchange_authorization_code(self, auth_code: str, code_verifier: str = "") -> Tuple[bool, str]:
        """Đổi mã Authorization Code (lấy từ OAuth flow lần đầu) lấy Access & Refresh Token"""
        if not self.app_id or not self.secret_key:
            return False, "Thiếu ZALO_APP_ID hoặc ZALO_SECRET_KEY trong cấu hình."

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "secret_key": self.secret_key,
        }
        data = {
            "code": auth_code,
            "app_id": self.app_id,
            "grant_type": "authorization_code",
        }
        if code_verifier:
            data["code_verifier"] = code_verifier

        try:
            res = requests.post(ZALO_OAUTH_TOKEN_URL, headers=headers, data=data, timeout=15)
            payload = res.json()
            if "access_token" in payload and "refresh_token" in payload:
                self.save_tokens(
                    access_token=payload["access_token"],
                    refresh_token=payload["refresh_token"],
                    expires_in=int(payload.get("expires_in", 90000)),
                )
                return True, "Khởi tạo Zalo Token thành công!"
            else:
                err_msg = payload.get("error_description") or payload.get("message") or str(payload)
                return False, f"Lỗi từ Zalo OAuth: {err_msg}"
        except Exception as e:
            return False, f"Lỗi kết nối khi đổi code: {e}"

    def refresh_access_token(self) -> Tuple[bool, str]:
        """Tự động dùng Refresh Token hiện tại để cấp lại Access Token và Refresh Token mới"""
        current_refresh_token = self._tokens.get("refresh_token") or os.getenv("ZALO_OA_REFRESH_TOKEN", "")
        if not current_refresh_token:
            return False, "Chưa có Refresh Token. Vui lòng chạy bước cấp quyền OAuth ban đầu."

        if not self.app_id or not self.secret_key:
            return False, "Thiếu ZALO_APP_ID hoặc ZALO_SECRET_KEY trong cấu hình."

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "secret_key": self.secret_key,
        }
        data = {
            "refresh_token": current_refresh_token,
            "app_id": self.app_id,
            "grant_type": "refresh_token",
        }

        try:
            logger.info("Đang gọi Zalo OAuth API để làm mới Access Token...")
            res = requests.post(ZALO_OAUTH_TOKEN_URL, headers=headers, data=data, timeout=15)
            payload = res.json()

            if "access_token" in payload and "refresh_token" in payload:
                self.save_tokens(
                    access_token=payload["access_token"],
                    refresh_token=payload["refresh_token"],
                    expires_in=int(payload.get("expires_in", 90000)),
                )
                logger.info("Làm mới Zalo Access Token thành công!")
                return True, self._tokens["access_token"]
            else:
                err_desc = payload.get("error_description") or payload.get("message") or str(payload)
                logger.error(f"Không thể làm mới token Zalo: {err_desc}")
                return False, f"Zalo OAuth Error: {err_desc}"
        except Exception as e:
            logger.error(f"Lỗi mạng khi kết nối Zalo OAuth: {e}")
            return False, f"Network Error: {e}"

    def get_access_token(self) -> str:
        """
        Lấy Access Token hợp lệ.
        Nếu token sắp hết hạn hoặc đã hết hạn, tự động gọi refresh trước khi trả về.
        """
        if self.is_token_valid():
            return self._tokens.get("access_token", "")

        logger.warning("Zalo Access Token đã hết hạn hoặc sắp hết hạn. Đang tự động làm mới...")
        ok, res = self.refresh_access_token()
        if ok:
            return res
        # Nếu refresh thất bại, vẫn trả về token cũ (có thể may mắn chưa chết hẳn) hoặc rỗng
        return self._tokens.get("access_token", "")


# Singleton instance
oauth_manager = ZaloOAuthManager()


if __name__ == "__main__":
    import sys

    print("=== KIỂM TRA ZALO OAUTH TOKEN MANAGER ===")
    token = oauth_manager.get_access_token()
    if token:
        print(f"Token hiện tại: {token[:15]}...{token[-10:]}")
        print(f"Hợp lệ: {oauth_manager.is_token_valid()}")
    else:
        print("Chưa có Access Token trong cấu hình.")
        print("Sử dụng lệnh: python zalo_oauth_manager.py --code <AUTH_CODE> để khởi tạo token.")
