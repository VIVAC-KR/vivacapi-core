"""create jobs table

Revision ID: 1c2f1b92a707
Revises: 78017752a05e
Create Date: 2026-05-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "1c2f1b92a707"
down_revision: Union[str, None] = "78017752a05e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("uid", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "type",
            sa.Enum(
                "spots_bulk_upsert",
                "spot_business_info_bulk_upsert",
                name="job_type",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "succeeded",
                "failed",
                name="job_status",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("result", JSONB, nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.uid"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(op.f("ix_jobs_status"), "jobs", ["status"])
    op.create_index(op.f("ix_jobs_created_at"), "jobs", ["created_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_jobs_created_at"), table_name="jobs")
    op.drop_index(op.f("ix_jobs_status"), table_name="jobs")
    op.drop_table("jobs")
    sa.Enum(name="job_type").drop(op.get_bind(), checkfirst=False)
    sa.Enum(name="job_status").drop(op.get_bind(), checkfirst=False)
