"""add consumer clipboard persistence tables

Revision ID: b2f4c7d9e1a0
Revises: 9h7e0f1g8d43
Create Date: 2026-06-18 18:35:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b2f4c7d9e1a0"
down_revision = "9h7e0f1g8d43"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "project_saved_providers" not in table_names:
        op.create_table(
            "project_saved_providers",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("provider_name", sa.String(length=140), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("project_id", "provider_name", name="uq_project_saved_provider"),
        )
        op.create_index(
            op.f("ix_project_saved_providers_project_id"),
            "project_saved_providers",
            ["project_id"],
            unique=False,
        )

    if "project_pinboard_items" not in table_names:
        op.create_table(
            "project_pinboard_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("label", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_project_pinboard_items_project_id"),
            "project_pinboard_items",
            ["project_id"],
            unique=False,
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "project_pinboard_items" in table_names:
        op.drop_index(op.f("ix_project_pinboard_items_project_id"), table_name="project_pinboard_items")
        op.drop_table("project_pinboard_items")

    if "project_saved_providers" in table_names:
        op.drop_index(op.f("ix_project_saved_providers_project_id"), table_name="project_saved_providers")
        op.drop_table("project_saved_providers")
