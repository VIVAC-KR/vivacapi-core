"""오픈채팅 정기 메시지 발송 기술 검증(VAC-1)용 임시 배치.
카카오는 오픈채팅에 메시지를 자동 발송하는 공식 API를 제공하지 않는다
(카카오 공식 확인: devtalk.kakao.com/t/api-api/150798). 대신 서버가 Slack
채널로 스팟 정보를 보내면, 사람이 그 내용을 오픈채팅에 수동으로 복붙한다.

독립 스크립트 + 호스트 crontab 패턴을 쓴다(신규 스케줄러 의존성 없음,
scripts/decay_trust_tier.py와 동일).

주기 실행 전제(호스트 crontab, 매일 09시):
    0 9 * * * cd /path/to/vivacapi-core && uv run python scripts/send_spots_slack.py >> /var/log/vivac/send_spots_slack.log 2>&1

수동 실행:
    uv run python scripts/send_spots_slack.py
"""

import asyncio
import logging

import httpx

from vivacapi.core.config import settings
from vivacapi.core.database import AsyncSessionLocal
from vivacapi.crud.spot import get_random_spots
from vivacapi.models.spot import Spot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SPOT_COUNT = 3


def _format_message(spots: list[Spot]) -> str:
    lines = ["*오늘의 야영장소*"]
    for spot in spots:
        region = " ".join(filter(None, [spot.region_province, spot.region_city]))
        line = f"- {spot.title}"
        if region:
            line += f" ({region})"
        if spot.booking_url:
            line += f" <{spot.booking_url}|예약 링크>"
        lines.append(line)
    return "\n".join(lines)


async def main() -> None:
    if not settings.SLACK_WEBHOOK_URL:
        logger.error("SLACK_WEBHOOK_URL 미설정 — 발송 중단")
        return

    async with AsyncSessionLocal() as session:
        spots = await get_random_spots(session, limit=SPOT_COUNT)

    if not spots:
        logger.info("발송할 스팟 없음")
        return

    message = _format_message(spots)
    async with httpx.AsyncClient() as client:
        response = await client.post(settings.SLACK_WEBHOOK_URL, json={"text": message})
        response.raise_for_status()

    logger.info("Slack 발송 완료: %s건", len(spots))


if __name__ == "__main__":
    asyncio.run(main())
