"""Add composite asset groups and auditable duplicate merges."""
from alembic import op
import sqlalchemy as sa

revision = "20260828_05"
down_revision = "20260826_04"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("assets") as batch:
        batch.add_column(sa.Column("is_group", sa.Boolean(), server_default="0", nullable=False))
        batch.add_column(sa.Column("parent_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("merged_into_id", sa.Integer(), nullable=True))
        batch.create_foreign_key("fk_assets_parent", "assets", ["parent_id"], ["id"], ondelete="SET NULL")
        batch.create_foreign_key("fk_assets_merged_into", "assets", ["merged_into_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_assets_parent_id", ["parent_id"])
        batch.create_index("ix_assets_merged_into_id", ["merged_into_id"])


def downgrade():
    with op.batch_alter_table("assets") as batch:
        batch.drop_index("ix_assets_merged_into_id")
        batch.drop_index("ix_assets_parent_id")
        batch.drop_constraint("fk_assets_merged_into", type_="foreignkey")
        batch.drop_constraint("fk_assets_parent", type_="foreignkey")
        batch.drop_column("merged_into_id")
        batch.drop_column("parent_id")
        batch.drop_column("is_group")
