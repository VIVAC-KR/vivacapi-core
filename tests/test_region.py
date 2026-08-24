from vivacapi.core.region import REGION_PROVINCE_WHITELIST, raw_names_for_region_filter


def test_region_province_whitelist_has_17_sido_codes():
    assert len(REGION_PROVINCE_WHITELIST) == 17


def test_raw_names_for_region_filter_covers_old_new_and_abbr_forms():
    names = raw_names_for_region_filter("강원")
    assert set(names) == {"강원도", "강원특별자치도", "강원"}


def test_raw_names_for_region_filter_rejects_unknown_code():
    assert raw_names_for_region_filter("강원도") == []
    assert raw_names_for_region_filter("해외") == []
