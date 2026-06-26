"""add consumer pending plan code

Revision ID: a1d2e3f4b5c6
Revises: f4d1c9a7b3e2
Create Date: 2026-06-25 15:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a1d2e3f4b5c6"
down_revision = "f4d1c9a7b3e2"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "subscriptions" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("subscriptions")}
    if "pending_plan_code" not in columns:
        with op.batch_alter_table("subscriptions", schema=None) as batch_op:
            batch_op.add_column(sa.Column("pending_plan_code", sa.String(length=40), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "subscriptions" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("subscriptions")}
    if "pending_plan_code" in columns:
        with op.batch_alter_table("subscriptions", schema=None) as batch_op:
            batch_op.drop_column("pending_plan_code")
