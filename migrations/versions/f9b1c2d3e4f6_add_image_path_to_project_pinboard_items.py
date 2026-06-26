"""add image_path to project_pinboard_items

Revision ID: f9b1c2d3e4f6
Revises: e8f1a2b3c4d5
Create Date: 2026-06-26 22:55:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f9b1c2d3e4f6"
down_revision = "e8f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "project_pinboard_items" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("project_pinboard_items")}
    if "image_path" not in columns:
        with op.batch_alter_table("project_pinboard_items", schema=None) as batch_op:
            batch_op.add_column(sa.Column("image_path", sa.String(length=500), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "project_pinboard_items" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("project_pinboard_items")}
    if "image_path" in columns:
        with op.batch_alter_table("project_pinboard_items", schema=None) as batch_op:
            batch_op.drop_column("image_path")
