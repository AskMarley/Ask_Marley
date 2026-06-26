"""add project lead metadata

Revision ID: b7c8d9e0f1a2
Revises: a1d2e3f4b5c6
Create Date: 2026-06-25 16:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b7c8d9e0f1a2"
down_revision = "a1d2e3f4b5c6"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "projects" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("projects")}
    with op.batch_alter_table("projects", schema=None) as batch_op:
        if "service_slug" not in columns:
            batch_op.add_column(sa.Column("service_slug", sa.String(length=80), nullable=True))
        if "location_code" not in columns:
            batch_op.add_column(sa.Column("location_code", sa.String(length=12), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "projects" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("projects")}
    with op.batch_alter_table("projects", schema=None) as batch_op:
        if "location_code" in columns:
            batch_op.drop_column("location_code")
        if "service_slug" in columns:
            batch_op.drop_column("service_slug")
