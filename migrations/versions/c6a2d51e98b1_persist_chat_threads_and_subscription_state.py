"""persist chat threads and subscription state

Revision ID: c6a2d51e98b1
Revises: b2f4c7d9e1a0
Create Date: 2026-06-19 09:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c6a2d51e98b1"
down_revision = "b2f4c7d9e1a0"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("chat_threads", schema=None) as batch_op:
        batch_op.alter_column("provider_id", existing_type=sa.Integer(), nullable=True)

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "chat_thread_pins" not in table_names:
        op.create_table(
            "chat_thread_pins",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("thread_id", sa.Integer(), nullable=False),
            sa.Column("label", sa.String(length=255), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["thread_id"], ["chat_threads.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_chat_thread_pins_thread_id"),
            "chat_thread_pins",
            ["thread_id"],
            unique=False,
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "chat_thread_pins" in table_names:
        op.drop_index(op.f("ix_chat_thread_pins_thread_id"), table_name="chat_thread_pins")
        op.drop_table("chat_thread_pins")

    with op.batch_alter_table("chat_threads", schema=None) as batch_op:
        batch_op.alter_column("provider_id", existing_type=sa.Integer(), nullable=False)
