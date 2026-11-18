"""quem mandou a última mensagem de cada conversa (a lista mostra embaixo do nome do contato)

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _quem_mandou(eu: bool, user_id, data) -> dict:
    """Mesma regra de ticketing.quem_mandou (a migração não importa o app)."""
    data = data if isinstance(data, dict) else {}
    if not eu:
        remetente = data.get('sender') if isinstance(data.get('sender'), dict) else {}
        nome = remetente.get('name') or remetente.get('number')
        return {'fromMe': False, 'name': nome} if nome else {'fromMe': False}
    if user_id:
        return {'fromMe': True, 'userId': user_id}
    if isinstance(data.get('api'), dict):
        return {'fromMe': True, 'via': 'api', 'name': data['api'].get('keyName')}
    if data.get('origin') == 'device':
        return {'fromMe': True, 'via': 'device'}
    return {'fromMe': True}


def upgrade() -> None:
    with op.batch_alter_table('contacts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_message_sender', sa.JSON(), nullable=True))

    # Conversas que já existem: pega a mensagem mais nova de cada uma (avisos do chamado não contam).
    bind = op.get_bind()
    contatos = sa.table(
        'contacts',
        sa.column('id', sa.String),
        sa.column('last_message_at', sa.DateTime(timezone=True)),
        sa.column('last_message_sender', sa.JSON),
    )
    mensagens = sa.table(
        'messages',
        sa.column('contact_id', sa.String),
        sa.column('user_id', sa.String),
        sa.column('is_from_me', sa.Boolean),
        sa.column('type', sa.String),
        sa.column('data', sa.JSON),
        sa.column('created_at', sa.DateTime(timezone=True)),
    )
    com_conversa = bind.execute(sa.select(contatos.c.id).where(contatos.c.last_message_at.is_not(None))).scalars().all()
    for cid in com_conversa:
        ultima = bind.execute(
            sa.select(mensagens.c.is_from_me, mensagens.c.user_id, mensagens.c.data)
            .where(mensagens.c.contact_id == cid, mensagens.c.type != 'ticket')
            .order_by(mensagens.c.created_at.desc())
            .limit(1)
        ).first()
        if ultima is not None:
            eu, user_id, data = ultima
            bind.execute(
                contatos.update().where(contatos.c.id == cid).values(last_message_sender=_quem_mandou(bool(eu), user_id, data))
            )


def downgrade() -> None:
    with op.batch_alter_table('contacts', schema=None) as batch_op:
        batch_op.drop_column('last_message_sender')
