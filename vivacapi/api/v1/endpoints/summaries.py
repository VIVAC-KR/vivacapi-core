# 라우터 데코레이터에 문자열을 직접 박지 않기 위한 summary 상수 모음.
# 라우터 파일명 기준으로 섹션을 나눈다.

# auth.py
GOOGLE_LOGIN_SUMMARY = "Google 로그인"
REFRESH_SUMMARY = "액세스 토큰 재발급"
ME_SUMMARY = "내 정보 조회"

# explore.py
LIST_SPOTS_SUMMARY = "스팟 목록/검색"
LIST_SPOTS_FOR_MAP_SUMMARY = "지도 핀 목록"
GET_SPOT_SUMMARY = "스팟 상세 조회"
LIST_SPOT_IMAGES_SUMMARY = "스팟 이미지 목록 조회"

# spot_reviews.py
CREATE_REVIEW_SUMMARY = "리뷰 작성"
LIST_REVIEWS_SUMMARY = "리뷰 목록 조회"
UPDATE_REVIEW_SUMMARY = "리뷰 수정"
DELETE_REVIEW_SUMMARY = "리뷰 삭제"
REPORT_REVIEW_SUMMARY = "리뷰 신고 접수"

# spot_groups.py
CREATE_GROUP_SUMMARY = "그룹 생성"
LIST_MY_GROUPS_SUMMARY = "내 그룹 목록 조회"
GET_GROUP_SUMMARY = "그룹 상세 조회"
UPDATE_GROUP_SUMMARY = "그룹 정보 수정"
DELETE_GROUP_SUMMARY = "그룹 삭제"
LIST_GROUP_SPOTS_SUMMARY = "그룹 스팟 목록 조회"
ADD_GROUP_SPOT_SUMMARY = "그룹에 스팟 추가"
REMOVE_GROUP_SPOT_SUMMARY = "그룹에서 스팟 제거"
LIST_GROUP_MEMBERS_SUMMARY = "그룹 멤버 목록 조회"
INVITE_GROUP_MEMBER_SUMMARY = "멤버 초대"
UPDATE_GROUP_MEMBER_ROLE_SUMMARY = "멤버 역할 변경"
REMOVE_GROUP_MEMBER_SUMMARY = "멤버 추방"

# invites.py
CREATE_INVITE_SUMMARY = "초대 링크 생성"
PREVIEW_INVITE_SUMMARY = "초대 링크 미리보기"
ACCEPT_INVITE_SUMMARY = "초대 링크 수락"

# conversations.py
CREATE_CONVERSATION_SUMMARY = "대화 생성"
LIST_CONVERSATIONS_SUMMARY = "내 대화 목록 조회"
GET_CONVERSATION_SUMMARY = "대화 상세 조회"
LIST_MESSAGES_SUMMARY = "메시지 목록 조회"
SEND_MESSAGE_SUMMARY = "메시지 전송"
MARK_CONVERSATION_READ_SUMMARY = "대화 읽음 처리"
DELETE_MESSAGE_SUMMARY = "메시지 삭제"

# user_blocks.py
BLOCK_USER_SUMMARY = "유저 차단"
UNBLOCK_USER_SUMMARY = "유저 차단 해제"

# admin_auth.py
ADMIN_GOOGLE_LOGIN_SUMMARY = "콘솔 staff Google 로그인"

# internal_jobs.py
GET_JOB_SUMMARY = "job 상태 조회"

# internal_db_dumps.py
ENQUEUE_DB_DUMP_SUMMARY = "DB 전체 덤프 작업 큐잉"
GET_DB_DUMP_DOWNLOAD_URL_SUMMARY = "완료된 DB 덤프 다운로드 URL 발급"

# internal_review_reports.py
LIST_REVIEW_REPORTS_SUMMARY = "리뷰 신고 목록 조회"

# internal_spots.py
GET_SPOT_HISTORY_SUMMARY = "스팟 변경 이력 조회"
LIST_SPOT_GROUPS_SUMMARY = "스팟이 속한 그룹 목록 조회"
ENQUEUE_SPOTS_BULK_UPSERT_SUMMARY = "스팟 대량 upsert 작업 큐잉"
LIST_SPOTS_ADMIN_SUMMARY = "스팟 어드민 목록 조회"
SPOT_STATS_SUMMARY = "스팟 대시보드 통계 조회"
ASSIGN_SPOTS_SUMMARY = "검증 대기 스팟 할당"
BULK_ASSIGN_SPOTS_SUMMARY = "스팟 할당 일괄 변경"
TRANSFER_SPOT_ASSIGNMENTS_SUMMARY = "스팟 할당 이전"
BULK_UPDATE_PIPELINE_STATUS_SUMMARY = "스팟 상태 일괄 변경 (SUPERUSER 전용)"
REASSIGN_SPOT_SUMMARY = "스팟 담당자 재할당"
DISTINCT_VALUES_SUMMARY = "필터 옵션 distinct 값 조회"
GET_SPOT_ADMIN_SUMMARY = "스팟 어드민 상세 조회"
UPDATE_SPOT_SUMMARY = "스팟 정보 수정"
DELETE_SPOT_SUMMARY = "스팟 소프트 삭제"
RESTORE_SPOT_SUMMARY = "소프트 삭제된 스팟 복구"

# internal_spot_images.py
PRESIGN_IMAGE_UPLOAD_SUMMARY = "업로드용 presigned URL 발급"
REGISTER_IMAGE_SUMMARY = "이미지 등록"

# internal_spot_business_info.py
GET_SPOT_BUSINESS_INFO_HISTORY_SUMMARY = "사업자정보 변경 이력 조회"
ENQUEUE_SPOT_BUSINESS_INFO_BULK_UPSERT_SUMMARY = "사업자정보 대량 업서트 등록"
LIST_BUSINESS_INFO_SUMMARY = "사업자정보 목록 조회"
GET_BUSINESS_INFO_SUMMARY = "사업자정보 단건 조회"
UPDATE_BUSINESS_INFO_SUMMARY = "사업자정보 수정"

# internal_spot_options.py
LIST_SPOT_OPTIONS_SUMMARY = "옵션값 목록 조회"
CREATE_SPOT_OPTION_SUMMARY = "옵션값 추가"
DELETE_SPOT_OPTION_SUMMARY = "옵션값 삭제"

# internal_spot_groups.py
CREATE_GROUP_ADMIN_SUMMARY = "그룹 생성"
LIST_GROUPS_ADMIN_SUMMARY = "그룹 목록 조회"
GET_GROUP_ADMIN_SUMMARY = "그룹 상세 조회"
UPDATE_GROUP_ADMIN_SUMMARY = "그룹 정보 수정"
DELETE_GROUP_ADMIN_SUMMARY = "그룹 삭제"
LIST_GROUP_MEMBERS_ADMIN_SUMMARY = "그룹 멤버 목록 조회"
ADD_GROUP_MEMBER_SUMMARY = "멤버 강제 추가"
UPDATE_GROUP_MEMBER_ROLE_ADMIN_SUMMARY = "멤버 역할 변경"
REMOVE_GROUP_MEMBER_ADMIN_SUMMARY = "멤버 추방"
LIST_GROUP_SPOTS_ADMIN_SUMMARY = "그룹 스팟 목록 조회"
ADD_GROUP_SPOT_ADMIN_SUMMARY = "그룹에 스팟 추가"
REMOVE_GROUP_SPOT_ADMIN_SUMMARY = "그룹 스팟 제거"
