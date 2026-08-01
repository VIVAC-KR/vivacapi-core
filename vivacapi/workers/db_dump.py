import asyncio
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from vivacapi.core.config import settings
from vivacapi.core.storage import upload_file

DUMP_S3_PREFIX = "db-dumps"


async def db_dump_handler(
    _db: AsyncSession, _payload: dict[str, Any]
) -> dict[str, Any]:
    """pg_dump(-Fc)로 전체 DB를 덤프해 S3에 업로드한다.

    --no-owner --no-privileges로 소유자/권한 정보를 제거해, DB_USER가 다른
    환경(dev/local/prod)에도 pg_restore로 그대로 적재할 수 있게 한다.
    """
    dump_id = uuid.uuid4().hex
    s3_key = f"{DUMP_S3_PREFIX}/{dump_id}.dump"

    with tempfile.TemporaryDirectory() as tmp_dir:
        dump_path = Path(tmp_dir) / "dump.pgcustom"

        env = os.environ.copy()
        env["PGPASSWORD"] = settings.DB_PASSWORD.get_secret_value()
        if settings.ENVIRONMENT == "prod":
            env["PGSSLMODE"] = "require"

        proc = await asyncio.create_subprocess_exec(
            "pg_dump",
            "-h", settings.DB_HOST,
            "-p", settings.DB_PORT,
            "-U", settings.DB_USER,
            "-d", settings.DB_NAME,
            "-Fc",
            "--no-owner",
            "--no-privileges",
            "-f", str(dump_path),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"pg_dump failed: {stderr.decode(errors='replace')}")

        size_bytes = dump_path.stat().st_size
        await upload_file(s3_key, str(dump_path))

    return {"s3_key": s3_key, "size_bytes": size_bytes, "format": "pg_dump-custom"}
