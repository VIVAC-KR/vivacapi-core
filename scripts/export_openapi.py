"""FastAPI 앱의 OpenAPI 3.x 명세를 docs/openapi.json으로 내보냅니다."""

import json
from pathlib import Path

from app.main import app

output = Path("docs/openapi.json")
output.parent.mkdir(parents=True, exist_ok=True)

spec = app.openapi()
output.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Exported: {output}  (OpenAPI {spec.get('openapi')})")
