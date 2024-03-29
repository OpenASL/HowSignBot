"""add jump_url

Revision ID: 5d3fdf926fe6
Revises: acd3a66644a2
Create Date: 2022-02-22 22:51:31.570397

"""
from alembic import op
import sqlalchemy as sa
import bot


# revision identifiers, used by Alembic.
revision = "5d3fdf926fe6"
down_revision = "acd3a66644a2"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column("star_logs", sa.Column("jump_url", sa.Text(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("star_logs", "jump_url")
    # ### end Alembic commands ###
