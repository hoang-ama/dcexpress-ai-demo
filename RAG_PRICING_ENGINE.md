# RAG PRICING ENGINE - QUY TẮC BẢNG GIÁ & TÍNH CƯỚC DC EXPRESS

Tài liệu này chi tiết hóa toàn bộ công thức tính cước, trọng lượng quy đổi và cấu trúc dữ liệu RAG cho các tuyến vận chuyển của DC Express.

---

## 1. CÔNG THỨC QUY ĐỔI TRỌNG LƯỢNG (VOLUMETRIC WEIGHT)

Theo quy định vận chuyển của DC Express, đối với hàng cồng kềnh có kích thước lớn hơn trọng lượng thực tế, cước phí được tính dựa trên **Trọng lượng tính cước**:

$$\text{Trọng lượng tính cước (kg)} = \max(\text{Trọng lượng thực tế (kg)}, \text{Trọng lượng quy đổi (kg)})$$

### A. Vận chuyển Đường Hàng Không (Nội địa & Liên sân bay)
$$\text{Trọng lượng quy đổi (kg)} = \frac{\text{Chiều dài (cm)} \times \text{Chiều rộng (cm)} \times \text{Chiều cao (cm)}}{6000}$$

### B. Vận chuyển Đường Bộ / Đường Sắt / Xe Tải / Cargo
$$\text{Trọng lượng quy đổi (kg)} = \frac{\text{Chiều dài (cm)} \times \text{Chiều rộng (cm)} \times \text{Chiều cao (cm)}}{5000}$$

---

## 2. CÔNG THỨC BÁO GIÁ VÀ CHÍNH SÁCH CHIẾT KHẤU

1. **Công thức Báo giá gốc cho Khách hàng**:
   $$\text{Giá báo Khách hàng} = \text{Giá gốc (trong Bảng giá chuẩn)} + 30\% \text{ (Phí quản lý \& Lợi nhuận)}$$
   *Ví dụ*: Tuyến Hà Nội - Quảng Ninh gói <=15kg có Giá gốc = 200.000 VNĐ.
   $\rightarrow \text{Giá báo Khách} = 200.000 + (200.000 \times 30\%) = 260.000 \text{ VNĐ}$.

2. **Chính sách Thương lượng / Giảm giá (CTKM)**:
   * Nếu khách không đồng ý báo giá lần 1, AI tự động giảm 10% trên Giá báo Khách:
   $$\text{Giá báo lần 2} = \text{Giá báo Khách lần 1} \times 90\%$$
   *Ví dụ*: $260.000 \times 0.9 = 234.000 \text{ VNĐ}$.
   * Nếu khách vẫn không đồng ý lần 2, AI tự động trigger nút **Chuyển cho Nhân viên tư vấn (Human Handover)**.

---

## 3. CẤU TRÚC KNOWLEDGE BASE RAG BẢNG GIÁ (MARKDOWN chuẩn hóa cho Vector DB)

Dữ liệu Bảng giá cước được lưu dưới dạng Markdown chuẩn hóa trong Dify / Vector DB để AI dễ dàng trích xuất (RAG Retrieval):

```markdown
# BẢNG CƯỚC VẬN CHUYỂN LIÊN TỈNH TỪ HÀ NỘI - DC EXPRESS (2024-2026)

## TUYẾN HÀ NỘI - QUẢNG NINH (HẠ LONG, UÔNG BÍ, CẨM PHẢ, ĐÔNG MAI)
- Loại dịch vụ: Chuyển phát Siêu tốc (4 - 6 giờ).
- Kiện nhỏ (Khối lượng <= 5kg, Kích thước <= 20x20x20cm): Giá gốc 150.000 VNĐ -> Giá báo khách: 195.000 VNĐ.
- Kiện vừa (Khối lượng <= 15kg, Kích thước <= 40x40x40cm): Giá gốc 200.000 VNĐ -> Giá báo khách: 260.000 VNĐ.
- Kiện to (Khối lượng <= 30kg, Kích thước <= 60x60x60cm): Giá gốc 250.000 VNĐ -> Giá báo khách: 325.000 VNĐ.
- Vượt 30kg: Tính thêm 8.000 VNĐ/kg phát sinh.

## TUYẾN HÀ NỘI - HẢI PHÒNG
- Loại dịch vụ: Siêu tốc (2 - 4 giờ).
- Kiện nhỏ (<= 5kg): Giá gốc 120.000 VNĐ -> Giá báo khách: 156.000 VNĐ.
- Kiện vừa (<= 15kg): Giá gốc 160.000 VNĐ -> Giá báo khách: 208.000 VNĐ.
- Kiện to (<= 30kg): Giá gốc 200.000 VNĐ -> Giá báo khách: 260.000 VNĐ.

## TUYẾN HÀ NỘI - TP. HỒ CHÍ MINH (SÂN BAY - SÂN BAY / TẬN TAY)
- Loại dịch vụ: Hỏa tốc Hàng không (6 - 12 giờ).
- Bưu kiện nhỏ (<= 2kg): Giá gốc 350.000 VNĐ -> Giá báo khách: 455.000 VNĐ.
- Bưu kiện vừa (<= 10kg): Giá gốc 550.000 VNĐ -> Giá báo khách: 715.000 VNĐ.
- Kiện hàng nặng (> 10kg): Giá gốc 45.000 VNĐ/kg -> Giá báo khách: 58.500 VNĐ/kg.

## PHỤ PHÍ VẬN CHUYỂN
- Phụ phí ngõ hẹp (xe tải/xe máy không vào tận nơi > 200m): +30.000 VNĐ.
- Phụ phí bốc xếp hàng nặng (> 30kg/kiện): +50.000 VNĐ/kiện.
- Phụ phí hẹn giờ chính xác (+/- 15 phút): +30.000 VNĐ.
```
