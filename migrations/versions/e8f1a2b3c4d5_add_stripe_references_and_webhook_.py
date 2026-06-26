"""add stripe references and webhook idempotency

Revision ID: e8f1a2b3c4d5
Revises: b7c8d9e0f1a2
Create Date: 2026-06-26 22:35:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e8f1a2b3c4d5"
down_revision = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "subscriptions" in table_names:
        columns = {column["name"] for column in inspector.get_columns("subscriptions")}
        with op.batch_alter_table("subscriptions", schema=None) as batch_op:
            if "stripe_customer_id" not in columns:
                batch_op.add_column(sa.Column("stripe_customer_id", sa.String(length=120), nullable=True))
            if "stripe_subscription_id" not in columns:
                batch_op.add_column(sa.Column("stripe_subscription_id", sa.String(length=120), nullable=True))
            if "stripe_price_id" not in columns:
                batch_op.add_column(sa.Column("stripe_price_id", sa.String(length=120), nullable=True))
            if "latest_invoice_id" not in columns:
                batch_op.add_column(sa.Column("latest_invoice_id", sa.String(length=120), nullable=True))
            if "latest_checkout_session_id" not in columns:
                batch_op.add_column(sa.Column("latest_checkout_session_id", sa.String(length=120), nullable=True))

        indexes = {index["name"] for index in inspector.get_indexes("subscriptions")}
        with op.batch_alter_table("subscriptions", schema=None) as batch_op:
            if "ix_subscriptions_stripe_customer_id" not in indexes:
                batch_op.create_index("ix_subscriptions_stripe_customer_id", ["stripe_customer_id"], unique=False)
            if "ix_subscriptions_stripe_subscription_id" not in indexes:
                batch_op.create_index("ix_subscriptions_stripe_subscription_id", ["stripe_subscription_id"], unique=False)

    if "stripe_webhook_events" not in table_names:
        op.create_table(
            "stripe_webhook_events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("stripe_event_id", sa.String(length=120), nullable=False),
            sa.Column("event_type", sa.String(length=120), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("stripe_event_id"),
        )
        op.create_index(
            "ix_stripe_webhook_events_stripe_event_id",
            "stripe_webhook_events",
            ["stripe_event_id"],
            unique=True,
        )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "stripe_webhook_events" in table_names:
        indexes = {index["name"] for index in inspector.get_indexes("stripe_webhook_events")}
        if "ix_stripe_webhook_events_stripe_event_id" in indexes:
            op.drop_index("ix_stripe_webhook_events_stripe_event_id", table_name="stripe_webhook_events")
        op.drop_table("stripe_webhook_events")

    if "subscriptions" in table_names:
        columns = {column["name"] for column in inspector.get_columns("subscriptions")}
        indexes = {index["name"] for index in inspector.get_indexes("subscriptions")}
        with op.batch_alter_table("subscriptions", schema=None) as batch_op:
            if "ix_subscriptions_stripe_subscription_id" in indexes:
                batch_op.drop_index("ix_subscriptions_stripe_subscription_id")
            if "ix_subscriptions_stripe_customer_id" in indexes:
                batch_op.drop_index("ix_subscriptions_stripe_customer_id")
            if "latest_checkout_session_id" in columns:
                batch_op.drop_column("latest_checkout_session_id")
            if "latest_invoice_id" in columns:
                batch_op.drop_column("latest_invoice_id")
            if "stripe_price_id" in columns:
                batch_op.drop_column("stripe_price_id")
            if "stripe_subscription_id" in columns:
                batch_op.drop_column("stripe_subscription_id")
            if "stripe_customer_id" in columns:
                batch_op.drop_column("stripe_customer_id")
