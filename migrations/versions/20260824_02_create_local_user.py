"""Create the single local user table."""
from alembic import op
import sqlalchemy as sa

revision = "20260824_02"
down_revision = "20260824_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "local_users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(500), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="1", nullable=False),
        sa.Column("failed_login_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime()),
        sa.Column("last_login_at", sa.DateTime()),
        sa.Column("session_id_hash", sa.String(64)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("local_users")