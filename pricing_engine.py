"""
Module: pricing_engine.py
Mục đích: Pricing Calculation Engine cho DC Express (Đi Chung Express).
Tính toán cước phí vận chuyển đường bộ, đường bay, nội thành,
quy đổi thể tích theo chuẩn logistics và tự động áp dụng biên lợi nhuận +30%.
"""

import re
from typing import Dict, Any, Optional, Tuple

# Danh sách một số tỉnh/thành phố lớn để nhận diện tuyến đường
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
    "thanh hóa": "mien_trung",
    "nghệ an": "mien_trung",
    "hà tĩnh": "mien_trung",
    "đà nẵng": "mien_trung",
    "huế": "mien_trung",
    "quảng nam": "mien_trung",
    "khánh hòa": "mien_trung",
    "nha trang": "mien_trung",
    "hồ chí minh": "mien_nam",
    "tp.hcm": "mien_nam",
    "tphcm": "mien_nam",
    "sài gòn": "mien_nam",
    "bình dương": "mien_nam",
    "đồng nai": "mien_nam",
    "cần thơ": "mien_nam",
    "long an": "mien_nam",
}

# Bảng giá cước đối tác gốc cơ sở (Base Cost - VNĐ)
# Tuyến đường bộ
BASE_TARIFF_ROAD = {
    "noi_thanh": {"base_2kg": 22000, "next_kg": 5000},
    "lien_tinh_cung_mien": {"base_2kg": 35000, "next_kg": 7000},     # Ví dụ HN -> Quảng Ninh
    "lien_tinh_khac_mien": {"base_2kg": 45000, "next_kg": 9000},     # Ví dụ HN -> Đà Nẵng / HCM
}

# Tuyến đường bay hỏa tốc (Air Express)
BASE_TARIFF_AIR = {
    "lien_tinh_khac_mien": {"base_2kg": 85000, "next_kg": 18000},    # HN -> HCM / Đà Nẵng
    "lien_tinh_cung_mien": {"base_2kg": 60000, "next_kg": 14000},
}


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
    """Tính cước theo bảng giá và trọng lượng tính cước."""
    weight = max(weight_kg, 0.5)
    base_2kg = tariff["base_2kg"]
    next_kg_rate = tariff["next_kg"]

    if weight <= 2.0:
        base_cost = base_2kg
    else:
        additional_weight = weight - 2.0
        base_cost = base_2kg + int(additional_weight * next_kg_rate)

    # Làm tròn giá gốc chục nghìn
    base_cost = int(round(base_cost, -2))
    
    # Công thức: Giá báo KH = (Giá gốc) + 30%
    customer_price = int(round(base_cost * (1 + margin_percent / 100), -3))

    return {
        "base_cost_vnd": base_cost,
        "customer_price_vnd": customer_price,
        "margin_percent": margin_percent,
        "profit_vnd": customer_price - base_cost,
    }


def estimate_pricing(
    sender_address: str,
    receiver_address: str,
    actual_weight_kg: float,
    cargo_description: str = "",
    dimensions: Optional[Tuple[float, float, float]] = None,
) -> Dict[str, Any]:
    """
    Hàm chính tính toán cước phí DC Express:
    - Trả về so sánh cả 2 dịch vụ (Đường bộ tiết kiệm & Đường bay hỏa tốc)
    - Tự động lấy trọng lượng tính cước lớn nhất giữa thực tế và quy đổi thể tích.
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

    # 2. Tính cước Đường bộ
    road_tariff = BASE_TARIFF_ROAD.get(route_type, BASE_TARIFF_ROAD["lien_tinh_khac_mien"])
    road_calc = calculate_service_cost(road_tariff, chargeable_road_kg, margin_percent=30.0)

    # 3. Tính cước Đường bay (Chỉ áp dụng nếu không phải nội thành)
    air_available = (route_type != "noi_thanh")
    air_calc = None
    if air_available:
        air_tariff = BASE_TARIFF_AIR.get(route_type, BASE_TARIFF_AIR["lien_tinh_khac_mien"])
        air_calc = calculate_service_cost(air_tariff, chargeable_air_kg, margin_percent=30.0)

    # Gợi ý dịch vụ mặc định: nếu hỏa tốc hoặc xa thì gợi ý cả 2, mặc định chọn đường bộ tiết kiệm
    recommended_service = "Đường bộ tiết kiệm"

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
                "estimated_delivery_time": "2 - 4 ngày" if route_type != "noi_thanh" else "Trong ngày",
            }
        },
        "recommended_service": recommended_service,
        "selected_quote": {
            "service_type": "Đường bộ tiết kiệm (DC Road)",
            "chargeable_weight_kg": chargeable_road_kg,
            "base_cost_vnd": road_calc["base_cost_vnd"],
            "customer_price_vnd": road_calc["customer_price_vnd"],
            "margin_percent": 30.0,
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
            "estimated_delivery_time": "12 - 24 giờ",
        }

    return result
