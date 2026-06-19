"""persist admin registry and moderation

Revision ID: f4d1c9a7b3e2
Revises: c6a2d51e98b1
Create Date: 2026-06-19 09:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f4d1c9a7b3e2"
down_revision = "c6a2d51e98b1"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("_alembic_tmp_providers"):
        op.execute(sa.text("DROP TABLE _alembic_tmp_providers"))
    if inspector.has_table("_alembic_tmp_taxonomy_entries"):
        op.execute(sa.text("DROP TABLE _alembic_tmp_taxonomy_entries"))

    provider_columns = {column["name"] for column in inspector.get_columns("providers")}
    if "billing_status" not in provider_columns:
        op.add_column(
            "providers",
            sa.Column(
                "billing_status",
                sa.String(length=30),
                nullable=False,
                server_default="active",
            ),
        )
    if "suspended" not in provider_columns:
        op.add_column(
            "providers",
            sa.Column(
                "suspended",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )

    taxonomy_columns = {column["name"] for column in inspector.get_columns("taxonomy_entries")}
    if "version" not in taxonomy_columns:
        op.add_column(
            "taxonomy_entries",
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        )

    if not inspector.has_table("taxonomy_versions"):
        op.create_table(
            "taxonomy_versions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("entry_id", sa.Integer(), nullable=False),
            sa.Column("actor", sa.String(length=120), nullable=False),
            sa.Column("reason", sa.String(length=255), nullable=False),
            sa.Column("before_path", sa.String(length=255), nullable=True),
            sa.Column("after_path", sa.String(length=255), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["entry_id"], ["taxonomy_entries.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    if "ix_taxonomy_versions_entry_id" not in {
        index["name"] for index in inspector.get_indexes("taxonomy_versions")
    }:
        op.create_index(op.f("ix_taxonomy_versions_entry_id"), "taxonomy_versions", ["entry_id"], unique=False)

    if not inspector.has_table("moderation_cases"):
        op.create_table(
            "moderation_cases",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("case_id", sa.String(length=20), nullable=False),
            sa.Column("reason", sa.String(length=255), nullable=False),
            sa.Column("participants", sa.String(length=255), nullable=False),
            sa.Column("severity", sa.String(length=20), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("source", sa.String(length=40), nullable=False),
            sa.Column("reported_by", sa.String(length=120), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("case_id"),
        )
    if "ix_moderation_cases_case_id" not in {
        index["name"] for index in inspector.get_indexes("moderation_cases")
    }:
        op.create_index(op.f("ix_moderation_cases_case_id"), "moderation_cases", ["case_id"], unique=True)


def downgrade():
    op.drop_index(op.f("ix_moderation_cases_case_id"), table_name="moderation_cases")
    op.drop_table("moderation_cases")

    op.drop_index(op.f("ix_taxonomy_versions_entry_id"), table_name="taxonomy_versions")
    op.drop_table("taxonomy_versions")

    with op.batch_alter_table("taxonomy_entries", schema=None) as batch_op:
        batch_op.drop_column("version")

    with op.batch_alter_table("providers", schema=None) as batch_op:
        batch_op.drop_column("suspended")
        batch_op.drop_column("billing_status")
