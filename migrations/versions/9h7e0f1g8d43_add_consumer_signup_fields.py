"""add consumer signup fields

Revision ID: 9h7e0f1g8d43
Revises: 8g6d9e0f7c32
Create Date: 2026-06-16 12:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9h7e0f1g8d43'
down_revision = '8g6d9e0f7c32'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('consumer_phone', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('consumer_postcode', sa.String(length=10), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('consumer_postcode')
        batch_op.drop_column('consumer_phone')
