import subprocess
import sys

# uvicorn은 uvicorn.* logger만 설정하고 root는 비워둔 채 남긴다 → main.py의
# basicConfig가 빠지면 앱 INFO 로그가 lastResort(WARNING)에 걸려 통째로 유실된다.
# pytest의 logging plugin이 root에 handler를 달아버려 in-process로는 이 회귀를
# 재현할 수 없으므로 subprocess로 격리해 검증한다.
_SCRIPT = """
import logging.config
import uvicorn.config

logging.config.dictConfig(uvicorn.config.LOGGING_CONFIG)

import vivacapi.main  # noqa: F401

logging.getLogger("vivacapi.workers.job_worker").info("worker-info-marker")
"""


def test_app_info_log_survives_uvicorn_config():
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT], capture_output=True, text=True
    )

    assert result.returncode == 0, result.stderr
    assert "worker-info-marker" in result.stderr
    assert "vivacapi.workers.job_worker" in result.stderr
