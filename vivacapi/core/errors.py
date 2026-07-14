from enum import StrEnum
from typing import Any

from fastapi import status


class ErrorCode(StrEnum):
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    SPOT_NOT_FOUND = "SPOT_NOT_FOUND"
    SPOT_BUSINESS_INFO_NOT_FOUND = "SPOT_BUSINESS_INFO_NOT_FOUND"
    CATEGORY_NOT_FOUND = "CATEGORY_NOT_FOUND"
    CATEGORY_ALREADY_EXISTS = "CATEGORY_ALREADY_EXISTS"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"


_DEFAULT_STATUS: dict[ErrorCode, int] = {
    ErrorCode.UNAUTHORIZED: status.HTTP_401_UNAUTHORIZED,
    ErrorCode.FORBIDDEN: status.HTTP_403_FORBIDDEN,
    ErrorCode.NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.USER_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.JOB_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.SPOT_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.SPOT_BUSINESS_INFO_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.CATEGORY_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.CATEGORY_ALREADY_EXISTS: status.HTTP_409_CONFLICT,
    ErrorCode.VALIDATION_ERROR: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ErrorCode.INTERNAL_ERROR: status.HTTP_500_INTERNAL_SERVER_ERROR,
    ErrorCode.SERVICE_UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
}


class AppException(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        status_code: int | None = None,
        details: Any | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code or _DEFAULT_STATUS[code]
        self.details = details
        super().__init__(message)
