"""Upload ENRICHED rows from vivacapi-etl spots_upload.csv to the local DB.

uid is assigned by the model default (shortuuid) — never taken from the CSV.

Run:
    uv run --env-file .env.local --with psycopg2-binary \
        python scripts/upload_spots_local.py
"""

import csv
import os
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from vivacapi.models.spot import Spot
from vivacapi.models.spot_business_info import SpotBusinessInfo

CSV_PATH = Path(__file__).resolve().parents[2] / "vivacapi-etl" / "data" / "spots_upload.csv"

SPOT_FIELDS = [
    "source", "external_id", "title", "address", "address_detail",
    "region_province", "region_city", "postal_code", "phone", "description",
    "tagline", "latitude", "longitude", "altitude", "unit_count",
    "is_fee_required", "is_pet_allowed", "pet_policy", "has_equipment_rental",
    "themes", "fire_pit_type", "amenities", "nearby_facilities",
    "camp_sight_type", "rating_avg", "review_count", "website_url",
    "booking_url", "features", "category", "total_area_m2",
    "has_liability_insurance", "pipeline_status", "trust_tier",
]
BIZ_FIELDS = [
    "business_reg_no", "tourism_business_reg_no", "business_type",
    "operation_type", "operating_agency", "operating_status",
    "national_park_no", "national_park_office_code", "national_park_serial_no",
    "national_park_category_code", "licensed_at",
]

ARRAY_FIELDS = {"has_equipment_rental", "themes", "amenities", "nearby_facilities", "category"}
BOOL_FIELDS = {"is_fee_required", "is_pet_allowed", "has_liability_insurance"}
FLOAT_FIELDS = {"latitude", "longitude", "altitude", "rating_avg", "total_area_m2"}
INT_FIELDS = {"unit_count", "review_count", "trust_tier", "national_park_no"}
DATE_FIELDS = {"licensed_at"}


def parse(field: str, raw: str):
    val = raw.strip()
    if val == "":
        return None
    if field in ARRAY_FIELDS:
        # pg literal {"a","b"} from transform_spots_csv.py
        return [x.strip().strip('"') for x in val.strip("{}").split('","')] if val != "{}" else None
    if field in BOOL_FIELDS:
        return val == "true"
    if field in FLOAT_FIELDS:
        return float(val)
    if field in INT_FIELDS:
        return int(val)
    if field in DATE_FIELDS:
        return date.fromisoformat(val)
    return val


def main() -> None:
    with CSV_PATH.open(encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if r["pipeline_status"] == "ENRICHED"]
    print(f"ENRICHED rows: {len(rows)}")
    assert len(rows) == 191, f"expected 191, got {len(rows)}"

    from urllib.parse import quote_plus

    url = (
        f"postgresql+psycopg2://{os.environ['DB_USER']}:{quote_plus(os.environ['DB_PASSWORD'])}"
        f"@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{os.environ['DB_NAME']}"
    )
    engine = create_engine(url)
    biz_count = 0
    with Session(engine) as session:
        for r in rows:
            spot = Spot(**{f: parse(f, r[f]) for f in SPOT_FIELDS})
            session.add(spot)
            session.flush()  # uid assigned by model default here

            biz_vals = {f: parse(f, r[f]) for f in BIZ_FIELDS}
            if any(v is not None for v in biz_vals.values()):
                session.add(SpotBusinessInfo(spot_uid=spot.uid, **biz_vals))
                biz_count += 1

        spots_n = session.scalar(select(func.count()).select_from(Spot))
        biz_n = session.scalar(select(func.count()).select_from(SpotBusinessInfo))
        session.commit()

    print(f"Inserted spots: {len(rows)} (table total {spots_n}), "
          f"spot_business_info: {biz_count} (table total {biz_n})")


if __name__ == "__main__":
    main()
