"""comandos.ja_batia: comando sem efeito vira status neutro

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-21 12:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('comandos', sa.Column('ja_batia', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    op.drop_column('comandos', 'ja_batia')
