"""hora da mensagem não lida mais antiga de cada conversa (a lista fica vermelha depois de 1h30)

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('contacts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('unread_since', sa.DateTime(timezone=True), nullable=True))

    # Conversas que já tinham não lidas: a mais antiga delas é a n-ésima mensagem do cliente,
    # contando da última para trás (n = quantas não lidas). Feito em Python porque o Postgres
    # não aceita OFFSET que dependa da linha de fora.
    bind = op.get_bind()
    contatos = sa.table(
        'contacts',
        sa.column('id', sa.String),
        sa.column('unread', sa.Integer),
        sa.column('last_message_at', sa.DateTime(timezone=True)),
        sa.column('unread_since', sa.DateTime(timezone=True)),
    )
    mensagens = sa.table(
        'messages',
        sa.column('contact_id', sa.String),
        sa.column('is_from_me', sa.Boolean),
        sa.column('created_at', sa.DateTime(timezone=True)),
    )
    pendentes = bind.execute(
        sa.select(contatos.c.id, contatos.c.unread, contatos.c.last_message_at).where(contatos.c.unread > 0)
    ).all()
    for cid, n, ultima in pendentes:
        desde = bind.execute(
            sa.select(mensagens.c.created_at)
            .where(mensagens.c.contact_id == cid, mensagens.c.is_from_me == sa.false())
            .order_by(mensagens.c.created_at.desc())
            .limit(1)
            .offset(max(0, n - 1))
        ).scalar()
        bind.execute(
            contatos.update().where(contatos.c.id == cid).values(unread_since=desde or ultima)
        )


def downgrade() -> None:
    with op.batch_alter_table('contacts', schema=None) as batch_op:
        batch_op.drop_column('unread_since')
