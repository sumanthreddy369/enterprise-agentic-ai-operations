"""Durable investigation submissions; preserve legacy placeholder rows."""

import sqlalchemy as sa
from alembic import op

revision = "0002_investigation_runs"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Additive operations avoid rebuilding a SQLite table referenced by foreign keys.
    op.add_column(
        "investigation_runs",
        sa.Column("tenant_id", sa.String(256), nullable=False, server_default="local"),
    )
    op.add_column(
        "investigation_runs",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("investigation_runs", sa.Column("question", sa.Text(), nullable=True))
    op.add_column("investigation_runs", sa.Column("submission_key", sa.String(64), nullable=True))
    op.add_column("investigation_runs", sa.Column("request_hash", sa.String(64), nullable=True))
    op.create_index(
        "uq_investigation_submission", "investigation_runs", ["submission_key"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_investigation_submission", table_name="investigation_runs")
    for name in ("request_hash", "submission_key", "question", "revision", "tenant_id"):
        op.drop_column("investigation_runs", name)
