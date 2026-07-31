"""Bộ mã lỗi chuẩn + exception dùng chung cho mọi API (A3).

12 mã lỗi lấy nguyên văn từ "Danh sách API CRM" mục XXXVI, cộng vài mã phụ đã
dùng từ A2 (ACCOUNT_LOCKED...). KHÔNG import FastAPI — services raise ApiError
thoải mái mà vẫn test chay được; đổi sang HTTP là việc của exception handler
trong app/main.py.

Cách dùng trong service:
    raise ApiError("NOT_FOUND", "Không tìm thấy nhân viên")
    raise ApiError("VALIDATION_ERROR", "Dữ liệu không hợp lệ",
                   errors={"email": "đã tồn tại"})
"""

# Mã lỗi -> mã HTTP. Nguồn: 12 mã chuẩn của đặc tả + phần mở rộng (ghi chú rõ).
ERROR_STATUS: dict[str, int] = {
    # --- 12 mã chuẩn của đặc tả ---
    "UNAUTHORIZED": 401,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "VALIDATION_ERROR": 422,
    "DUPLICATE_CUSTOMER": 409,
    "INVALID_STAGE_TRANSITION": 409,
    "MISSING_REQUIRED_DATA": 422,
    "TREATMENT_BLOCKED": 409,
    "CLINICAL_REVIEW_REQUIRED": 409,
    "COMPLIANCE_VIOLATION": 422,
    "INTEGRATION_ERROR": 502,
    "RATE_LIMITED": 429,
    # --- mở rộng (A2/A3) ---
    "ACCOUNT_LOCKED": 401,       # FR-001 khoá tạm do sai mật khẩu
    "ACCOUNT_DISABLED": 401,     # tài khoản inactive/suspended
    "NOT_IMPLEMENTED": 501,      # endpoint có trong đặc tả nhưng để giai đoạn sau
    "CONFLICT": 409,             # ràng buộc nghiệp vụ chung (vd còn khách chưa chuyển)
    "INTERNAL_ERROR": 500,
}


class ApiError(Exception):
    """Lỗi nghiệp vụ mang mã chuẩn. `errors` = chi tiết theo trường (nếu có)."""

    def __init__(self, code: str, message: str, errors: dict | None = None):
        if code not in ERROR_STATUS:
            raise ValueError(f"Mã lỗi lạ: {code} — thêm vào ERROR_STATUS trước")
        self.code = code
        self.message = message
        self.errors = errors or {}
        super().__init__(message)

    @property
    def http_status(self) -> int:
        return ERROR_STATUS[self.code]
