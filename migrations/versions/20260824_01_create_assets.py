"""Create assets table."""
from alembic import op
import sqlalchemy as sa

revision = "20260824_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(100)),
        sa.Column("purchase_date", sa.Date()),
        sa.Column("purchase_price", sa.Numeric(12, 2)),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_assets_name", "assets", ["name"])


def downgrade() -> None:
    op.drop_index("ix_assets_name", table_name="assets")
    op.drop_table("assets")
