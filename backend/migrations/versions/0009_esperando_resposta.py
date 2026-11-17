"""desde quando o cliente espera resposta de uma pessoa (a lista fica vermelha depois de 1h30)

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _resposta(eu: bool, tipo: str, data) -> bool:
    """Mesma regra de ticketing.conta_como_resposta (a migração não importa o app)."""
    if not eu or tipo == 'ticket':
        return False
    data = data if isinstance(data, dict) else {}
    return 'api' not in data and 'error' not in data


def upgrade() -> None:
    with op.batch_alter_table('contacts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('waiting_since', sa.DateTime(timezone=True), nullable=True))

    # Conversas com chamado aberto: anda das mensagens mais novas para as mais velhas até achar
    # a última resposta nossa; a mensagem do cliente mais antiga depois dela é o início da espera.
    bind = op.get_bind()
    contatos = sa.table(
        'contacts',
        sa.column('id', sa.String),
        sa.column('current_ticket_id', sa.String),
        sa.column('waiting_since', sa.DateTime(timezone=True)),
    )
    mensagens = sa.table(
        'messages',
        sa.column('contact_id', sa.String),
        sa.column('is_from_me', sa.Boolean),
        sa.column('type', sa.String),
        sa.column('data', sa.JSON),
        sa.column('created_at', sa.DateTime(timezone=True)),
    )
    abertos = bind.execute(sa.select(contatos.c.id).where(contatos.c.current_ticket_id.is_not(None))).scalars().all()
    for cid in abertos:
        linhas = bind.execute(
            sa.select(mensagens.c.is_from_me, mensagens.c.type, mensagens.c.data, mensagens.c.created_at)
            .where(mensagens.c.contact_id == cid)
            .order_by(mensagens.c.created_at.desc())
            .limit(300)
        ).all()
        desde = None
        for eu, tipo, data, quando in linhas:
            if _resposta(bool(eu), tipo, data):
                break
            if not eu:
                desde = quando
        if desde is not None:
            bind.execute(contatos.update().where(contatos.c.id == cid).values(waiting_since=desde))


def downgrade() -> None:
    with op.batch_alter_table('contacts', schema=None) as batch_op:
        batch_op.drop_column('waiting_since')
