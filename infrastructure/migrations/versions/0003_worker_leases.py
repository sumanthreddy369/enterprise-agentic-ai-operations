"""Fenced worker leases and atomic report persistence."""

import sqlalchemy as sa
from alembic import op

revision = "0003_worker_leases"
down_revision = "0002_investigation_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("investigation_runs", sa.Column("lease_token", sa.String(36), nullable=True))
    op.add_column(
        "investigation_runs", sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "investigation_runs",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("investigation_runs", sa.Column("report", sa.JSON(), nullable=True))


def downgrade() -> None:
    for name in ("report", "attempts", "lease_until", "lease_token"):
        op.drop_column("investigation_runs", name)
