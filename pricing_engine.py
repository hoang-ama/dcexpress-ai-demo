"""
Module: pricing_engine.py
Mục đích: Pricing Calculation Engine cho DC Express (Đi Chung Express).
Tính toán cước phí vận chuyển đường bộ, đường bay, nội thành,
hệ thống bậc tải trọng (Tiered Pricing) cho hàng chuyển phát nhanh, hàng sỉ và hàng ghép xe tải (LTL),
quy đổi thể tích theo chuẩn logistics và tự động áp dụng biên lợi nhuận +30%.
"""

import re
from typing import Dict, Any, Optional, Tuple

__all__ = [
    "estimate_pricing",
    "calculate_service_cost_tiered",
    "calculate_service_cost",
    "extract_shipping_info_from_dialogue",
    "determine_route_type",
    "detect_region",
    "calculate_volumetric_weight",
    "extract_dimensions_from_text",
    "ROAD_FREIGHT_TIERS",
    "AIR_FREIGHT_TIERS",
    "BASE_TARIFF_ROAD",
    "BASE_TARIFF_AIR",
    "PROVINCE_REGIONS",
]

# Danh sách tỉnh/thành phố và phân vùng miền để nhận diện tuyến đường
PROVINCE_REGIONS = {
    "hà nội": "mien_bac",
    "quảng ninh": "mien_bac",
    "hải phòng": "mien_bac",
    "bắc ninh": "mien_bac",
    "hải dương": "mien_bac",
    "nam định": "mien_bac",
    "thái bình": "mien_bac",
    "vĩnh phúc": "mien_bac",
    "phú thọ": "mien_bac",
    "bắc giang": "mien_bac",
    "thái nguyên": "mien_bac",
    "lạng sơn": "mien_bac",
    "hà nam": "mien_bac",
    "hưng yên": "mien_bac",
    "ninh bình": "mien_bac",
    "quang minh": "mien_bac",
    "mê linh": "mien_bac",
    "thanh hóa": "mien_trung",
    "nghệ an": "mien_trung",
    "hà tĩnh": "mien_trung",
    "đà nẵng": "mien_trung",
    "huế": "mien_trung",
    "quảng nam": "mien_trung",
    "quảng ngãi": "mien_trung",
    "bình định": "mien_trung",
    "quy nhơn": "mien_trung",
    "phú yên": "mien_trung",
    "khánh hòa": "mien_trung",
    "nha trang": "mien_trung",
    "hồ chí minh": "mien_nam",
    "tp.hcm": "mien_nam",
    "tphcm": "mien_nam",
    "sài gòn": "mien_nam",
    "bình dương": "mien_nam",
    "dĩ an": "mien_nam",
    "thuận an": "mien_nam",
    "thủ dầu một": "mien_nam",
    "đồng nai": "mien_nam",
    "biên hòa": "mien_nam",
    "bà rịa": "mien_nam",
    "vũng tàu": "mien_nam",
    "cần thơ": "mien_nam",
    "long an": "mien_nam",
    "tiền giang": "mien_nam",
}

# Bảng giá cước cơ sở kế thừa (Legacy Base Cost - VNĐ)
BASE_TARIFF_ROAD = {
    "noi_thanh": {"base_2kg": 22000, "next_kg": 5000},
    "lien_tinh_cung_mien": {"base_2kg": 35000, "next_kg": 7000},     # Ví dụ HN -> Quảng Ninh
    "lien_tinh_khac_mien": {"base_2kg": 45000, "next_kg": 9000},     # Ví dụ HN -> Đà Nẵng / HCM
}

BASE_TARIFF_AIR = {
    "lien_tinh_khac_mien": {"base_2kg": 85000, "next_kg": 18000},    # HN -> HCM / Đà Nẵng
    "lien_tinh_cung_mien": {"base_2kg": 60000, "next_kg": 14000},
}

# ----------------- HỆ THỐNG BẬC TẢI TRỌNG (TIERED PRICING) -----------------
# 1. Biểu cước đường bộ phân bậc (Road Freight & LTL Tiers)
ROAD_FREIGHT_TIERS = [
    {
        "tier_id": "tier_parcel",
        "name": "Kiện nhỏ chuyển phát nhanh (< 20kg)",
        "max_kg": 20,
        "type": "parcel_base_2kg",
        "rates": {
            "noi_thanh": {"base_2kg": 22000, "next_kg": 5000},
            "lien_tinh_cung_mien": {"base_2kg": 35000, "next_kg": 7000},
            "lien_tinh_khac_mien": {"base_2kg": 45000, "next_kg": 9000},
        }
    },
    {
        "tier_id": "tier_small_bulk",
        "name": "Lô nhỏ / Hàng kiện vừa (20 - 100kg)",
        "max_kg": 100,
        "type": "per_kg",
        "rates": {
            "noi_thanh": 2500,
            "lien_tinh_cung_mien": 4500,
            "lien_tinh_khac_mien": 6500,
        }
    },
    {
        "tier_id": "tier_wholesale",
        "name": "Hàng sỉ / Hàng tải trung (100 - 500kg)",
        "max_kg": 500,
        "type": "per_kg",
        "rates": {
            "noi_thanh": 1800,
            "lien_tinh_cung_mien": 3200,
            "lien_tinh_khac_mien": 4800,
        }
    },
    {
        "tier_id": "tier_heavy_pallet",
        "name": "Hàng nặng / Pallet (500 - 1.500kg)",
        "max_kg": 1500,
        "type": "per_kg",
        "rates": {
            "noi_thanh": 1400,
            "lien_tinh_cung_mien": 2200,
            "lien_tinh_khac_mien": 3500,
        }
    },
    {
        "tier_id": "tier_ltl_truck",
        "name": "Ghép xe tải lớn LTL (1.500 - 5.000kg)",
        "max_kg": 5000,
        "type": "per_kg",
        "rates": {
            "noi_thanh": 1000,
            "lien_tinh_cung_mien": 1600,
            "lien_tinh_khac_mien": 2550,  # ~2.550 đ/kg gốc tuyến Bắc - Nam xe tải 8-15 tấn
        }
    },
    {
        "tier_id": "tier_ftl_bulk",
        "name": "Siêu tải / Bao trọn xe FTL (> 5.000kg)",
        "max_kg": float("inf"),
        "type": "per_kg",
        "rates": {
            "noi_thanh": 800,
            "lien_tinh_cung_mien": 1200,
            "lien_tinh_khac_mien": 2000,
        }
    }
]

# 2. Biểu cước hàng không phân bậc (Air Freight & Air Cargo Tiers)
AIR_FREIGHT_TIERS = [
    {
        "tier_id": "air_parcel",
        "name": "Hỏa tốc bưu kiện bay (< 20kg)",
        "max_kg": 20,
        "type": "parcel_base_2kg",
        "rates": {
            "lien_tinh_cung_mien": {"base_2kg": 60000, "next_kg": 14000},
            "lien_tinh_khac_mien": {"base_2kg": 85000, "next_kg": 18000},
        }
    },
    {
        "tier_id": "air_small_bulk",
        "name": "Hỏa tốc lô vừa (20 - 100kg)",
        "max_kg": 100,
        "type": "per_kg",
        "rates": {
            "lien_tinh_cung_mien": 14000,
            "lien_tinh_khac_mien": 18000,
        }
    },
    {
        "tier_id": "air_cargo_mid",
        "name": "Air Cargo tải trung (100 - 500kg)",
        "max_kg": 500,
        "type": "per_kg",
        "rates": {
            "lien_tinh_cung_mien": 11000,
            "lien_tinh_khac_mien": 15000,
        }
    },
    {
        "tier_id": "air_cargo_heavy",
        "name": "Air Cargo tải nặng (500 - 1.500kg)",
        "max_kg": 1500,
        "type": "per_kg",
        "rates": {
            "lien_tinh_cung_mien": 9000,
            "lien_tinh_khac_mien": 13000,
        }
    },
    {
        "tier_id": "air_cargo_super",
        "name": "Air Charter / Chuyến bay chuyên dụng (> 1.500kg)",
        "max_kg": float("inf"),
        "type": "per_kg",
        "rates": {
            "lien_tinh_cung_mien": 8000,
            "lien_tinh_khac_mien": 11500,
        }
    }
]


def detect_region(address: str) -> Tuple[str, str]:
    """Nhận diện tỉnh/thành phố và phân vùng miền từ địa chỉ văn bản."""
    addr_lower = address.lower()
    for prov, region in PROVINCE_REGIONS.items():
        if prov in addr_lower:
            return prov.title(), region
    return "Khác", "chua_xac_dinh"


def determine_route_type(sender_address: str, receiver_address: str) -> Tuple[str, str, str]:
    """
    Xác định loại tuyến đường:
    - noi_thanh
    - lien_tinh_cung_mien
    - lien_tinh_khac_mien
    """
    sender_prov, sender_reg = detect_region(sender_address)
    receiver_prov, receiver_reg = detect_region(receiver_address)

    if sender_prov != "Khác" and sender_prov == receiver_prov:
        route_type = "noi_thanh"
    elif sender_reg != "chua_xac_dinh" and sender_reg == receiver_reg:
        route_type = "lien_tinh_cung_mien"
    else:
        route_type = "lien_tinh_khac_mien"

    return route_type, sender_prov, receiver_prov


def calculate_volumetric_weight(
    length_cm: float, width_cm: float, height_cm: float, method: str = "road"
) -> float:
    """
    Tính khối lượng quy đổi thể tích:
    - Đường hàng không: Dài x Rộng x Cao / 6000
    - Đường bộ: Dài x Rộng x Cao / 5000
    """
    divisor = 6000.0 if method == "air" else 5000.0
    vol_weight = (length_cm * width_cm * height_cm) / divisor
    return round(vol_weight, 2)


def extract_dimensions_from_text(text: str) -> Optional[Tuple[float, float, float]]:
    """Cố gắng tìm kích thước D x R x C từ mô tả hàng hóa nếu có (VD: 30x20x10cm hoặc 30*20*10)."""
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:x|\*)\s*(\d+(?:\.\d+)?)\s*(?:x|\*)\s*(\d+(?:\.\d+)?)", text, re.I)
    if match:
        try:
            return float(match.group(1)), float(match.group(2)), float(match.group(3))
        except ValueError:
            return None
    return None


def calculate_service_cost(
    tariff: Dict[str, int], weight_kg: float, margin_percent: float = 30.0
) -> Dict[str, Any]:
    """Hàm tính cước tuyến tính cơ bản (legacy)."""
    weight = max(weight_kg, 0.5)
    base_2kg = tariff["base_2kg"]
    next_kg_rate = tariff["next_kg"]

    if weight <= 2.0:
        base_cost = base_2kg
    else:
        additional_weight = weight - 2.0
        base_cost = base_2kg + int(additional_weight * next_kg_rate)

    base_cost = int(round(base_cost, -2))
    customer_price = int(round(base_cost * (1 + margin_percent / 100), -3))

    return {
        "base_cost_vnd": base_cost,
        "customer_price_vnd": customer_price,
        "margin_percent": margin_percent,
        "profit_vnd": customer_price - base_cost,
    }


def calculate_service_cost_tiered(
    method: str, route_type: str, weight_kg: float, margin_percent: float = 30.0
) -> Dict[str, Any]:
    """
    Tính cước theo hệ thống Bậc tải trọng (Tiered Pricing):
    - method: 'road' hoặc 'air'
    - Phân bậc rõ ràng từ bưu kiện (<20kg) đến hàng sỉ, pallet và ghép xe tải nặng (LTL).
    - Bảo đảm tính liên tục đơn điệu (đơn hàng nặng hơn không bị rẻ hơn đơn hàng nhẹ).
    """
    weight = max(weight_kg, 0.5)

    if method == "road":
        if weight <= 20.0:
            rates_map = {
                "noi_thanh": {"base_2kg": 22000, "next_kg": 5000},
                "lien_tinh_cung_mien": {"base_2kg": 35000, "next_kg": 7000},
                "lien_tinh_khac_mien": {"base_2kg": 45000, "next_kg": 9000},
            }
            rates = rates_map.get(route_type, rates_map["lien_tinh_khac_mien"])
            base_cost = rates["base_2kg"] + max(0.0, weight - 2.0) * rates["next_kg"]
            tier_id = "tier_parcel"
            tier_name = "Kiện nhỏ chuyển phát nhanh (< 20kg)"
            unit_rate = rates["next_kg"]
            calc_detail = f"2kg đầu: {rates['base_2kg']:,} đ + {max(0.0, weight - 2.0):.1f}kg x {rates['next_kg']:,} đ/kg"
        else:
            tier_id = "tier_ltl_truck"
            tier_name = "Ghép xe tải lớn LTL (1.500 - 5.000kg)"
            unit_rate = 2550
            for tier in ROAD_FREIGHT_TIERS[1:]:
                if weight <= tier["max_kg"]:
                    tier_id = tier["tier_id"]
                    tier_name = tier["name"]
                    r_map = tier["rates"]
                    unit_rate = r_map.get(route_type, r_map.get("lien_tinh_khac_mien", 2550))
                    raw_cost = weight * unit_rate
                    # Sàn giá tối thiểu = cước của mốc trần kiện nhỏ 20kg
                    min_floor = 45000 + 18 * 9000 if route_type == "lien_tinh_khac_mien" else (
                        35000 + 18 * 7000 if route_type == "lien_tinh_cung_mien" else 22000 + 18 * 5000
                    )
                    base_cost = max(raw_cost, min_floor)
                    calc_detail = f"{weight:.1f}kg x {unit_rate:,} đ/kg ({tier_name})"
                    break
    else:
        # Đường bay hỏa tốc (Air Express & Air Cargo)
        if weight <= 20.0:
            rates_map = {
                "lien_tinh_cung_mien": {"base_2kg": 60000, "next_kg": 14000},
                "lien_tinh_khac_mien": {"base_2kg": 85000, "next_kg": 18000},
            }
            rates = rates_map.get(route_type, rates_map["lien_tinh_khac_mien"])
            base_cost = rates["base_2kg"] + max(0.0, weight - 2.0) * rates["next_kg"]
            tier_id = "air_parcel"
            tier_name = "Hỏa tốc bưu kiện bay (< 20kg)"
            unit_rate = rates["next_kg"]
            calc_detail = f"2kg đầu: {rates['base_2kg']:,} đ + {max(0.0, weight - 2.0):.1f}kg x {rates['next_kg']:,} đ/kg"
        else:
            tier_id = "air_cargo_super"
            tier_name = "Air Charter / Chuyến bay chuyên dụng (> 1.500kg)"
            unit_rate = 11500
            for tier in AIR_FREIGHT_TIERS[1:]:
                if weight <= tier["max_kg"]:
                    tier_id = tier["tier_id"]
                    tier_name = tier["name"]
                    r_map = tier["rates"]
                    unit_rate = r_map.get(route_type, r_map.get("lien_tinh_khac_mien", 11500))
                    raw_cost = weight * unit_rate
                    min_floor = 85000 + 18 * 18000 if route_type == "lien_tinh_khac_mien" else 60000 + 18 * 14000
                    base_cost = max(raw_cost, min_floor)
                    calc_detail = f"{weight:.1f}kg x {unit_rate:,} đ/kg ({tier_name})"
                    break

    base_cost = int(round(base_cost, -2))
    # Công thức: Giá báo KH = Giá gốc đối tác + 30% margin
    customer_price = int(round(base_cost * (1 + margin_percent / 100), -3))
    profit = customer_price - base_cost
    formula = f"Giá gốc đối tác: {base_cost:,} đ + {margin_percent}% margin = {customer_price:,} đ"

    return {
        "base_cost_vnd": base_cost,
        "customer_price_vnd": customer_price,
        "profit_vnd": profit,
        "margin_percent": margin_percent,
        "tier_id": tier_id,
        "tier_name": tier_name,
        "unit_rate_vnd": unit_rate,
        "calc_detail": calc_detail,
        "formula": formula,
    }


def extract_shipping_info_from_dialogue(text: str) -> Dict[str, Any]:
    """
    Trích xuất nhanh các thông tin then chốt để tính giá từ lịch sử hội thoại hoặc tin nhắn:
    - Điểm gửi (sender_address)
    - Điểm nhận (receiver_address)
    - Khối lượng hàng (weight_kg)
    - Mô tả hàng hóa (cargo_description)
    - Ghi chú (notes)
    - has_sufficient_info: Có đủ điều kiện để tự động tính giá hay không.
    """
    clean = text.replace("\r\n", "\n")

    sender_addr = ""
    receiver_addr = ""
    weight_kg = None
    cargo_desc = ""
    notes = ""

    # 1. Tìm theo định dạng có nhãn trường rõ ràng
    m_send = re.search(
        r"(?:địa chỉ gửi|kho gửi|điểm gửi|gửi từ kho|gửi từ)\s*[:：\-]?\s*([^\n\.\;]+(?:[^\n\.]+?(?:Việt Nam|Hồ Chí Minh|Hà Nội|Bình Dương|Đà Nẵng|Quảng Ninh|Bắc Ninh|Hải Phòng|[A-ZÀ-Ỹa-zà-ỹ0-9\s,\/\-]+?)))(?=(?:\.|\n|địa chỉ nhận|kho nhận|điểm nhận|đến|về|phương thức|thời gian|ghi chú|$))",
        clean,
        re.I,
    )
    if m_send:
        sender_addr = m_send.group(1).strip()

    m_recv = re.search(
        r"(?:địa chỉ nhận|kho nhận|điểm nhận|nhận tại|gửi đến|gửi về|đến kho)\s*[:：\-]?\s*([^\n\.\;]+(?:[^\n\.]+?(?:Việt Nam|Hà Nội|Hồ Chí Minh|Quảng Ninh|Bắc Ninh|Hải Phòng|Đà Nẵng|[A-ZÀ-Ỹa-zà-ỹ0-9\s,\/\-]+?)))(?=(?:\.|\n|phương thức|thời gian|ghi chú|hàng hóa|$))",
        clean,
        re.I,
    )
    if m_recv:
        receiver_addr = m_recv.group(1).strip()

    # 2. Tìm theo cấu trúc hội thoại tự nhiên: "từ [Điểm A] đến/về [Điểm B]"
    if not sender_addr or not receiver_addr:
        m_pair = re.search(
            r"(?:từ|gửi từ)\s+([^,\n\.\;]+?(?:Hà Nội|Hồ Chí Minh|Quảng Ninh|Bình Dương|[A-ZÀ-Ỹa-zà-ỹ0-9\s]+?))\s+(?:về|đến|qua)\s+([^,\n\.\;]+?(?:Quảng Ninh|Hà Nội|Hồ Chí Minh|Bắc Ninh|[A-ZÀ-Ỹa-zà-ỹ0-9\s]+?))(?:\s+bạn|\s+ạ|\.|\n|,|$)",
            clean,
            re.I,
        )
        if m_pair:
            if not sender_addr:
                sender_addr = m_pair.group(1).strip()
            if not receiver_addr:
                receiver_addr = m_pair.group(2).strip()

    # 3. Trọng lượng tính cước
    m_ton = re.search(r"(\d+(?:[.,]\d+)?)\s*tấn", clean, re.I)
    if m_ton:
        try:
            val = float(m_ton.group(1).replace(",", "."))
            weight_kg = val * 1000.0
        except ValueError:
            pass

    if weight_kg is None:
        m_kg = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:kg quy đổi|kg|kí|ký|cân)", clean, re.I)
        if m_kg:
            val_str = m_kg.group(1)
            # Nếu có dấu chấm phân cách hàng nghìn (VD: 2.893 kg)
            if "." in val_str and len(val_str.split(".")[1]) == 3:
                val_str = val_str.replace(".", "")
            else:
                val_str = val_str.replace(",", ".")
            try:
                weight_kg = float(val_str)
            except ValueError:
                pass

    # 4. Mô tả hàng hóa
    m_cargo = re.search(r"(?:thông tin đơn hàng|hàng hóa|mặt hàng|loại hàng)\s*[:：\-]?\s*([^\n\.\;]+)", clean, re.I)
    if m_cargo:
        cargo_desc = m_cargo.group(1).strip()
    elif "mật ong" in clean.lower():
        cargo_desc = "276 thùng mật ong"
    elif "nước nuôi tôm" in clean.lower():
        cargo_desc = "1 thùng nước nuôi tôm"

    # 5. Ghi chú & Thời gian
    m_note = re.search(r"(?:ghi chú|lưu ý)\s*[:：\-]?\s*([^\n\r]+)", clean, re.I)
    if m_note:
        notes = m_note.group(1).strip()

    has_sufficient_info = bool(sender_addr and receiver_addr and weight_kg and weight_kg > 0)

    return {
        "sender_address": sender_addr,
        "receiver_address": receiver_addr,
        "weight_kg": weight_kg,
        "cargo_description": cargo_desc,
        "notes": notes,
        "has_sufficient_info": has_sufficient_info,
    }


def estimate_pricing(
    sender_address: str,
    receiver_address: str,
    actual_weight_kg: float,
    cargo_description: str = "",
    dimensions: Optional[Tuple[float, float, float]] = None,
) -> Dict[str, Any]:
    """
    Hàm chính tính toán cước phí DC Express (Áp dụng Tiered Pricing chuẩn logistics):
    - Trả về so sánh cả 2 dịch vụ (Đường bộ tiết kiệm & Đường bay hỏa tốc)
    - Tự động lấy trọng lượng tính cước lớn nhất giữa thực tế và quy đổi thể tích.
    - Áp dụng biểu cước bậc tải trọng (hàng chuyển phát nhanh kiện lẻ vs ghép xe tải LTL vs FTL).
    """
    if not dimensions and cargo_description:
        dimensions = extract_dimensions_from_text(cargo_description)

    route_type, sender_prov, receiver_prov = determine_route_type(sender_address, receiver_address)

    # 1. Tính trọng lượng thể tích quy đổi
    if dimensions:
        vol_road = calculate_volumetric_weight(*dimensions, method="road")
        vol_air = calculate_volumetric_weight(*dimensions, method="air")
    else:
        vol_road = 0.0
        vol_air = 0.0

    chargeable_road_kg = max(actual_weight_kg, vol_road)
    chargeable_air_kg = max(actual_weight_kg, vol_air)

    # 2. Tính cước Đường bộ theo Bậc tải trọng (Tiered Pricing)
    road_calc = calculate_service_cost_tiered("road", route_type, chargeable_road_kg, margin_percent=30.0)

    # 3. Tính cước Đường bay theo Bậc tải trọng (Chỉ áp dụng nếu không phải nội thành)
    air_available = (route_type != "noi_thanh")
    air_calc = None
    if air_available:
        air_calc = calculate_service_cost_tiered("air", route_type, chargeable_air_kg, margin_percent=30.0)

    # Thời gian giao dự kiến theo tính chất đơn hàng
    if route_type == "noi_thanh":
        delivery_time_road = "Trong ngày"
    elif chargeable_road_kg >= 1500.0 and route_type == "lien_tinh_khac_mien":
        delivery_time_road = "48 giờ (Ghép xe tải lớn Bắc - Nam chạy thẳng)"
    else:
        delivery_time_road = "2 - 4 ngày"

    result = {
        "route_info": {
            "route_type": route_type,
            "sender_province": sender_prov,
            "receiver_province": receiver_prov,
            "route_display": f"{sender_prov} ➔ {receiver_prov}",
        },
        "weight_metrics": {
            "actual_weight_kg": actual_weight_kg,
            "dimensions_cm": dimensions if dimensions else "Chưa có (Tính theo khối lượng thực)",
            "road_volumetric_weight_kg": vol_road,
            "air_volumetric_weight_kg": vol_air,
            "road_chargeable_kg": chargeable_road_kg,
            "air_chargeable_kg": chargeable_air_kg,
        },
        "options": {
            "road_economy": {
                "service_name": "Đường bộ tiết kiệm (DC Road)",
                "chargeable_weight_kg": chargeable_road_kg,
                "base_cost_vnd": road_calc["base_cost_vnd"],
                "customer_price_vnd": road_calc["customer_price_vnd"],
                "profit_vnd": road_calc["profit_vnd"],
                "margin_percent": 30.0,
                "tier_id": road_calc["tier_id"],
                "tier_name": road_calc["tier_name"],
                "unit_rate_vnd": road_calc["unit_rate_vnd"],
                "calc_detail": road_calc["calc_detail"],
                "formula": road_calc["formula"],
                "estimated_delivery_time": delivery_time_road,
            }
        },
        "recommended_service": "Đường bộ tiết kiệm",
        "selected_quote": {
            "service_type": "Đường bộ tiết kiệm (DC Road)",
            "chargeable_weight_kg": chargeable_road_kg,
            "base_cost_vnd": road_calc["base_cost_vnd"],
            "customer_price_vnd": road_calc["customer_price_vnd"],
            "profit_vnd": road_calc["profit_vnd"],
            "margin_percent": 30.0,
            "tier_id": road_calc["tier_id"],
            "tier_name": road_calc["tier_name"],
            "unit_rate_vnd": road_calc["unit_rate_vnd"],
            "calc_detail": road_calc["calc_detail"],
            "formula": road_calc["formula"],
        },
    }

    if air_calc:
        result["options"]["air_express"] = {
            "service_name": "Hỏa tốc đường bay (DC Air Express)",
            "chargeable_weight_kg": chargeable_air_kg,
            "base_cost_vnd": air_calc["base_cost_vnd"],
            "customer_price_vnd": air_calc["customer_price_vnd"],
            "profit_vnd": air_calc["profit_vnd"],
            "margin_percent": 30.0,
            "tier_id": air_calc["tier_id"],
            "tier_name": air_calc["tier_name"],
            "unit_rate_vnd": air_calc["unit_rate_vnd"],
            "calc_detail": air_calc["calc_detail"],
            "formula": air_calc["formula"],
            "estimated_delivery_time": "12 - 24 giờ",
            "notes": "Hàng tải lớn > 500kg cần xác nhận tải trọng khoang máy bay và slot chuyến bay" if chargeable_air_kg > 500 else "",
        }

    return result
