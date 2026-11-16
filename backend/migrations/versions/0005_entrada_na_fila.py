"""hora em que o chamado entrou na fila (a Fila mostra primeiro quem espera há mais tempo)

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('queued_at', sa.DateTime(timezone=True), nullable=True))
    # Chamados que já existiam: contam a partir da abertura
    op.execute("UPDATE tickets SET queued_at = started_at WHERE queued_at IS NULL")


def downgrade() -> None:
    with op.batch_alter_table('tickets', schema=None) as batch_op:
        batch_op.drop_column('queued_at')
