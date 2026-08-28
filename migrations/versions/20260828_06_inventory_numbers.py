"""Add generated inventory numbers."""
from alembic import op
import sqlalchemy as sa

revision = "20260828_06"
down_revision = "20260828_05"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("assets") as batch:
        batch.add_column(sa.Column("inventory_number", sa.String(length=32), nullable=True))
    op.execute("UPDATE assets SET inventory_number = printf('HAM-%06d', id) WHERE inventory_number IS NULL")
    with op.batch_alter_table("assets") as batch:
        batch.create_index("ix_assets_inventory_number", ["inventory_number"], unique=True)


def downgrade():
    with op.batch_alter_table("assets") as batch:
        batch.drop_index("ix_assets_inventory_number")
        batch.drop_column("inventory_number")
