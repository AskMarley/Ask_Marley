"""add provider signup fields

Revision ID: 8g6d9e0f7c32
Revises: 7f5c0a9e6b21
Create Date: 2026-06-16 12:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8g6d9e0f7c32'
down_revision = '7f5c0a9e6b21'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('company_name', sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column('phone', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('business_reg_number', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('service_categories', sa.String(length=500), nullable=True))
        batch_op.add_column(sa.Column('travel_postcodes', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('insurance_verified', sa.Boolean(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('provider_status', sa.String(length=30), nullable=True, server_default='pending'))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('provider_status')
        batch_op.drop_column('insurance_verified')
        batch_op.drop_column('travel_postcodes')
        batch_op.drop_column('service_categories')
        batch_op.drop_column('business_reg_number')
        batch_op.drop_column('phone')
        batch_op.drop_column('company_name')
