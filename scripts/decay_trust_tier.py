"""trust_tier 신선도 감쇠 배치. docs/backlog.md "DB 백업 이중화"와 동일하게
독립 스크립트 + 호스트 crontab 패턴을 쓴다(신규 스케줄러 의존성 없음).

주기 실행 전제(호스트 crontab, 주 1회면 충분 — threshold 180일 대비 과함):
    0 4 * * 0 cd /path/to/vivacapi-core && uv run python scripts/decay_trust_tier.py >> /var/log/vivac/decay_trust_tier.log 2>&1

수동 실행:
    uv run python scripts/decay_trust_tier.py
"""

import asyncio
import logging

from vivacapi.core.database import AsyncSessionLocal
from vivacapi.crud.spot import decay_stale_trust_tiers

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    async with AsyncSessionLocal() as session:
        result = await decay_stale_trust_tiers(session)
    logger.info("trust_tier decay 완료: %s", result)


if __name__ == "__main__":
    asyncio.run(main())
