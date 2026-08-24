# 광역시도 풀네임 → 약칭 매핑. 개편 전후 명칭(강원도/강원특별자치도 등)을 모두 키로 등록해
# DB에 어느 시점 데이터가 남아 있든 동일한 약칭으로 변환되게 한다.
SIDO_ABBR: dict[str, str] = {
    "서울특별시": "서울",
    "부산광역시": "부산",
    "대구광역시": "대구",
    "인천광역시": "인천",
    "광주광역시": "광주",
    "대전광역시": "대전",
    "울산광역시": "울산",
    "세종특별자치시": "세종",
    "경기도": "경기",
    "강원도": "강원",
    "강원특별자치도": "강원",
    "충청북도": "충북",
    "충청남도": "충남",
    "전라북도": "전북",
    "전북특별자치도": "전북",
    "전라남도": "전남",
    "경상북도": "경북",
    "경상남도": "경남",
    "제주특별자치도": "제주",
}


def abbreviate_sido(region_province: str | None) -> str | None:
    """광역시도 풀네임을 약칭으로 변환한다. 매핑에 없으면 원본을 그대로 반환한다."""
    if region_province is None:
        return None
    return SIDO_ABBR.get(region_province, region_province)


# region_province 필터 화이트리스트. 코드=라벨(약칭 그대로) — SpotOptionField처럼
# ASCII 코드/한글 라벨을 분리하지 않는다. region_short 응답값과 동일한 값을 그대로
# 필터로 되돌려 보내는 왕복이 가능해야 프론트가 별도 변환 없이 재사용할 수 있다.
REGION_PROVINCE_WHITELIST: frozenset[str] = frozenset(SIDO_ABBR.values())

# 약칭 → DB region_province 컬럼에 실제 있을 수 있는 원본 값 목록.
# 신구 지명(강원도/강원특별자치도 등)과, 이미 약칭으로 저장된 값까지 모두
# 같은 약칭으로 묶어 등호 필터가 아닌 in() 매칭에 쓴다.
_RAW_NAMES_BY_ABBR: dict[str, list[str]] = {
    abbr: [abbr] for abbr in REGION_PROVINCE_WHITELIST
}
for _raw, _abbr in SIDO_ABBR.items():
    _RAW_NAMES_BY_ABBR[_abbr].append(_raw)


def raw_names_for_region_filter(abbr: str) -> list[str]:
    """필터 약칭에 대응하는 DB 원본 값 목록. 화이트리스트 밖 값이면 빈 리스트."""
    return _RAW_NAMES_BY_ABBR.get(abbr, [])
