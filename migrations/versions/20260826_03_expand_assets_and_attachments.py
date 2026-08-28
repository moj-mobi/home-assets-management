"""Expand asset details and add shared attachments."""
from alembic import op
import sqlalchemy as sa

revision = "20260826_03"
down_revision = "20260824_02"
branch_labels = None
depends_on = None

FIELDS = [
    ("manufacturer", sa.String(150)), ("model", sa.String(150)), ("serial_number", sa.String(150)),
    ("purchase_condition", sa.String(20)), ("received_date", sa.Date()), ("currency", sa.String(3)),
    ("seller", sa.String(200)), ("seller_type", sa.String(20)), ("purchase_country", sa.String(100)),
    ("product_url", sa.String(1000)), ("invoice_number", sa.String(150)), ("order_number", sa.String(150)),
    ("location", sa.String(150)), ("status", sa.String(20)), ("conformity_months", sa.Integer()),
    ("conformity_start", sa.Date()), ("conformity_end", sa.Date()), ("conformity_source", sa.String(20)),
    ("warranty_provider", sa.String(200)), ("warranty_months", sa.Integer()), ("warranty_start", sa.Date()),
    ("warranty_end", sa.Date()), ("warranty_number", sa.String(150)), ("warranty_terms_url", sa.String(1000)),
    ("warranty_notes", sa.Text()),
]

def upgrade():
    with op.batch_alter_table("assets") as batch:
        for name, kind in FIELDS: batch.add_column(sa.Column(name, kind, nullable=True))
    op.execute("UPDATE assets SET currency='EUR' WHERE currency IS NULL")
    op.execute("UPDATE assets SET status='in_use' WHERE status IS NULL")
    op.create_table("attachments", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("original_name", sa.String(255), nullable=False), sa.Column("stored_name", sa.String(100), nullable=False, unique=True), sa.Column("document_type", sa.String(30), nullable=False), sa.Column("mime_type", sa.String(100), nullable=False), sa.Column("size", sa.Integer(), nullable=False), sa.Column("uploaded_at", sa.DateTime(), server_default=sa.func.now(), nullable=False), sa.Column("confirmed", sa.Boolean(), server_default="0", nullable=False))
    op.create_table("asset_attachments", sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True), sa.Column("attachment_id", sa.Integer(), sa.ForeignKey("attachments.id", ondelete="CASCADE"), primary_key=True))

def downgrade():
    op.drop_table("asset_attachments"); op.drop_table("attachments")
    with op.batch_alter_table("assets") as batch:
        for name, _ in reversed(FIELDS): batch.drop_column(name)
