"""Add soft archiving and normalize retired status code."""
from alembic import op
import sqlalchemy as sa

revision = "20260826_04"
down_revision = "20260826_03"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("assets") as batch:
        batch.add_column(sa.Column("archived_at", sa.DateTime(), nullable=True))
    op.execute("UPDATE assets SET status='destroyed' WHERE status='discarded'")
    op.execute("UPDATE assets SET archived_at=CURRENT_TIMESTAMP WHERE status='stored' AND archived_at IS NULL")

def downgrade():
    op.execute("UPDATE assets SET status='discarded' WHERE status='destroyed'")
    with op.batch_alter_table("assets") as batch:
        batch.drop_column("archived_at")
