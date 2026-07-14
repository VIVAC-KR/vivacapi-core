"""add user staff_role

Revision ID: b3d8f2a4c6e1
Revises: e5c7d9a1b3f4
Create Date: 2026-07-14 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b3d8f2a4c6e1"
down_revision: Union[str, None] = "e5c7d9a1b3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_staff_role_enum = sa.Enum("staff", "manager", "superuser", name="staff_role")


def upgrade() -> None:
    _staff_role_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "users",
        sa.Column(
            "staff_role",
            sa.Enum(
                "staff", "manager", "superuser", name="staff_role", create_type=False
            ),
            server_default="staff",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "staff_role")
    _staff_role_enum.drop(op.get_bind(), checkfirst=True)
