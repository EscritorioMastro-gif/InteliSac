"""gasto do botão Corrigir (Claude) e saldo da Anthropic informado pelo administrador

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'corretor_conta',
        sa.Column('account_id', sa.String(length=36), sa.ForeignKey('accounts.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('mes', sa.String(length=7), nullable=False, server_default=''),
        sa.Column('gasto_mes_usd', sa.Float(), nullable=False, server_default='0'),
        sa.Column('correcoes_mes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('saldo_usd', sa.Float(), nullable=True),
        sa.Column('saldo_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('gasto_desde_saldo_usd', sa.Float(), nullable=False, server_default='0'),
        sa.Column('aviso_abaixo_usd', sa.Float(), nullable=False, server_default='3'),
        sa.Column('sem_credito_em', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('corretor_conta')
