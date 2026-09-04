"""add_raw_api_key_to_device

Revision ID: 8e4be0b0902a
Revises: 0006_health_device
Create Date: 2026-09-01 09:36:51.589348

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8e4be0b0902a'
down_revision: Union[str, None] = '0006_health_device'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('device', sa.Column('raw_api_key', sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column('device', 'raw_api_key')
