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
    SPOT_IMAGE_NOT_FOUND = "SPOT_IMAGE_NOT_FOUND"
    SPOT_BUSINESS_INFO_NOT_FOUND = "SPOT_BUSINESS_INFO_NOT_FOUND"
    SPOT_OPTION_NOT_FOUND = "SPOT_OPTION_NOT_FOUND"
    SPOT_OPTION_ALREADY_EXISTS = "SPOT_OPTION_ALREADY_EXISTS"
    SPOT_GROUP_NOT_FOUND = "SPOT_GROUP_NOT_FOUND"
    SPOT_GROUP_MEMBER_NOT_FOUND = "SPOT_GROUP_MEMBER_NOT_FOUND"
    SPOT_GROUP_MEMBER_ALREADY_EXISTS = "SPOT_GROUP_MEMBER_ALREADY_EXISTS"
    SPOT_GROUP_SPOT_ALREADY_EXISTS = "SPOT_GROUP_SPOT_ALREADY_EXISTS"
    SPOT_GROUP_LAST_OWNER_REQUIRED = "SPOT_GROUP_LAST_OWNER_REQUIRED"
    SPOT_GROUP_INVITE_NOT_ALLOWED = "SPOT_GROUP_INVITE_NOT_ALLOWED"
    REVIEW_NOT_FOUND = "REVIEW_NOT_FOUND"
    REVIEW_ALREADY_EXISTS = "REVIEW_ALREADY_EXISTS"
    REVIEW_REPORT_ALREADY_EXISTS = "REVIEW_REPORT_ALREADY_EXISTS"
    INVITE_NOT_FOUND = "INVITE_NOT_FOUND"
    INVITE_NOT_ACCEPTABLE = "INVITE_NOT_ACCEPTABLE"
    CONVERSATION_NOT_FOUND = "CONVERSATION_NOT_FOUND"
    MESSAGE_NOT_FOUND = "MESSAGE_NOT_FOUND"
    USER_BLOCKED = "USER_BLOCKED"
    DB_DUMP_NOT_READY = "DB_DUMP_NOT_READY"
    CURSOR_SCOPE_MISMATCH = "CURSOR_SCOPE_MISMATCH"
    RATE_LIMITED = "RATE_LIMITED"
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
    ErrorCode.SPOT_IMAGE_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.SPOT_BUSINESS_INFO_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.SPOT_OPTION_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.SPOT_OPTION_ALREADY_EXISTS: status.HTTP_409_CONFLICT,
    ErrorCode.SPOT_GROUP_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.SPOT_GROUP_MEMBER_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.SPOT_GROUP_MEMBER_ALREADY_EXISTS: status.HTTP_409_CONFLICT,
    ErrorCode.SPOT_GROUP_SPOT_ALREADY_EXISTS: status.HTTP_409_CONFLICT,
    ErrorCode.SPOT_GROUP_LAST_OWNER_REQUIRED: status.HTTP_409_CONFLICT,
    ErrorCode.SPOT_GROUP_INVITE_NOT_ALLOWED: status.HTTP_403_FORBIDDEN,
    ErrorCode.REVIEW_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.REVIEW_ALREADY_EXISTS: status.HTTP_409_CONFLICT,
    ErrorCode.REVIEW_REPORT_ALREADY_EXISTS: status.HTTP_409_CONFLICT,
    ErrorCode.INVITE_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.INVITE_NOT_ACCEPTABLE: status.HTTP_409_CONFLICT,
    ErrorCode.CONVERSATION_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.MESSAGE_NOT_FOUND: status.HTTP_404_NOT_FOUND,
    ErrorCode.USER_BLOCKED: status.HTTP_403_FORBIDDEN,
    ErrorCode.DB_DUMP_NOT_READY: status.HTTP_409_CONFLICT,
    ErrorCode.CURSOR_SCOPE_MISMATCH: status.HTTP_400_BAD_REQUEST,
    ErrorCode.RATE_LIMITED: status.HTTP_429_TOO_MANY_REQUESTS,
    ErrorCode.VALIDATION_ERROR: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ErrorCode.INTERNAL_ERROR: status.HTTP_500_INTERNAL_SERVER_ERROR,
    ErrorCode.SERVICE_UNAVAILABLE: status.HTTP_503_SERVICE_UNAVAILABLE,
}


def sanitize_exc_message(exc: BaseException, max_len: int = 500) -> str:
    """예외를 job.result/job.error에 담아도 되는 형태로 줄인다.

    SQLAlchemy는 str(exc)에 실행한 SQL 전문과 바인딩된 파라미터를 함께 붙인다 —
    그대로 저장하면 job 조회 권한(STAFF)만으로 스키마와 입력값을 읽을 수 있다.
    `[SQL:` 이후를 잘라 사람이 읽을 원인 메시지만 남긴다. 전문은 로그에만 남긴다.
    """
    message = str(exc).split("\n[SQL:", 1)[0].strip()
    reason = f"{type(exc).__name__}: {message}" if message else type(exc).__name__
    return reason[:max_len] + "..." if len(reason) > max_len else reason


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
