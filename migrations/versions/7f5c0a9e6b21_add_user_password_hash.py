"""add user password hash

Revision ID: 7f5c0a9e6b21
Revises: d1a66179c636
Create Date: 2026-06-15 17:25:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7f5c0a9e6b21'
down_revision = 'd1a66179c636'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('password_hash', sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('password_hash')
