"""add audit_log + triggers for spots, spot_business_info

Revision ID: b7f3a1c9d2e4
Revises: 0dd988c6b130
Create Date: 2026-07-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b7f3a1c9d2e4'
down_revision: Union[str, None] = '0dd988c6b130'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 감사 대상 테이블. 새 테이블을 추적하려면 여기에 추가하고 새 마이그레이션에서 트리거만 부착.
AUDITED_TABLES = ("spots", "spot_business_info")


def upgrade() -> None:
    # asyncpg는 한 execute에 여러 커맨드를 못 넣으므로 문장마다 분리한다.
    op.execute(
        """
        CREATE TABLE audit_log (
            id          bigserial PRIMARY KEY,
            table_name  text        NOT NULL,
            row_uid     text        NOT NULL,
            action      text        NOT NULL,
            old_data    jsonb,
            new_data    jsonb,
            changed_by  text,
            changed_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_audit_log_row ON audit_log (table_name, row_uid, changed_at)"
    )
    # AFTER 트리거라 반환값은 무시된다. changed_by는 트랜잭션에서
    # `SET LOCAL app.user_id = '...'`를 설정하지 않으면 NULL로 남는다.
    op.execute(
        """
        CREATE FUNCTION log_audit() RETURNS trigger AS $$
        BEGIN
            INSERT INTO audit_log(
                table_name, row_uid, action, old_data, new_data, changed_by
            )
            VALUES (
                TG_TABLE_NAME,
                COALESCE(NEW.uid, OLD.uid),
                TG_OP,
                CASE WHEN TG_OP <> 'INSERT' THEN to_jsonb(OLD) END,
                CASE WHEN TG_OP <> 'DELETE' THEN to_jsonb(NEW) END,
                current_setting('app.user_id', true)
            );
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in AUDITED_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER audit_{table}
                AFTER INSERT OR UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION log_audit();
            """
        )


def downgrade() -> None:
    for table in AUDITED_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS audit_{table} ON {table};")
    op.execute("DROP FUNCTION IF EXISTS log_audit();")
    op.execute("DROP TABLE IF EXISTS audit_log;")
