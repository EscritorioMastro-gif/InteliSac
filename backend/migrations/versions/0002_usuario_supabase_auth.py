"""usuario supabase auth: liga cada usuário do InteliSac ao usuário do Supabase Auth

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-13 13:35:41.962913

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('auth_user_id', sa.String(length=36), nullable=True))
        batch_op.create_unique_constraint('uq_users_auth_user_id', ['auth_user_id'])


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_constraint('uq_users_auth_user_id', type_='unique')
        batch_op.drop_column('auth_user_id')
