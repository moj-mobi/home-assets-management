"""Add background AI asset valuations."""
from alembic import op
import sqlalchemy as sa

revision = "20260829_07"
down_revision = "20260828_06"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("assets") as batch:
        batch.add_column(sa.Column("estimated_model_year_min", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("estimated_model_year_max", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("estimated_purchase_price", sa.Numeric(12, 2), nullable=True))
        batch.add_column(sa.Column("estimated_market_value_eu_min", sa.Numeric(12, 2), nullable=True))
        batch.add_column(sa.Column("estimated_market_value_eu_max", sa.Numeric(12, 2), nullable=True))
        batch.add_column(sa.Column("estimated_market_value_si_min", sa.Numeric(12, 2), nullable=True))
        batch.add_column(sa.Column("estimated_market_value_si_max", sa.Numeric(12, 2), nullable=True))
        batch.add_column(sa.Column("estimated_warranty_likelihood", sa.String(30), nullable=True))
        batch.add_column(sa.Column("estimate_confidence", sa.Numeric(4, 3), nullable=True))
        batch.add_column(sa.Column("estimate_sources_json", sa.Text(), nullable=True))
        batch.add_column(sa.Column("estimate_rationale", sa.Text(), nullable=True))
        batch.add_column(sa.Column("estimated_at", sa.DateTime(), nullable=True))
    op.create_table("asset_valuation_jobs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("batch_id", sa.String(36), nullable=False), sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False), sa.Column("status", sa.String(20), nullable=False, server_default="queued"), sa.Column("error_message", sa.Text()), sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False), sa.Column("started_at", sa.DateTime()), sa.Column("completed_at", sa.DateTime()))
    op.create_index("ix_asset_valuation_jobs_batch_id", "asset_valuation_jobs", ["batch_id"])
    op.create_index("ix_asset_valuation_jobs_asset_id", "asset_valuation_jobs", ["asset_id"])
    op.create_index("ix_asset_valuation_jobs_status", "asset_valuation_jobs", ["status"])


def downgrade():
    op.drop_table("asset_valuation_jobs")
    with op.batch_alter_table("assets") as batch:
        for name in ("estimated_at", "estimate_rationale", "estimate_sources_json", "estimate_confidence", "estimated_warranty_likelihood", "estimated_market_value_si_max", "estimated_market_value_si_min", "estimated_market_value_eu_max", "estimated_market_value_eu_min", "estimated_purchase_price", "estimated_model_year_max", "estimated_model_year_min"):
            batch.drop_column(name)
