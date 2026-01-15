"""add audit columns on user table

Revision ID: cf770f0b94ee
Revises: 4707e7fd074d
Create Date: 2026-01-10 21:22:19.401280

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from api.models.base import get_audit_columns


# revision identifiers, used by Alembic.
revision: str = 'cf770f0b94ee'
down_revision: Union[str, Sequence[str], None] = '4707e7fd074d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('created_by', sa.DateTime(), nullable=False))
        batch_op.add_column(sa.Column('updated_by', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("deleted_by", sa.String, nullable=True))
        batch_op.add_column(sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')))
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

def downgrade() -> None:
    op.drop_column('users', 'created_by')
    op.drop_column('users', 'updated_by')
    op.drop_column('users', 'deleted_by')
    op.drop_column('users', 'created_at')
    op.drop_column('users', 'updated_at')
    op.drop_column('users', 'deleted_at')