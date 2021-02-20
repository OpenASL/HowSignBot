"""add participant email column

Revision ID: 052cd0f20b47
Revises: c56a6b9d6e85
Create Date: 2021-02-20 13:43:15.113175

"""
from alembic import op
import sqlalchemy as sa
import database


# revision identifiers, used by Alembic.
revision = "052cd0f20b47"
down_revision = "c56a6b9d6e85"
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column("zoom_participants", sa.Column("email", sa.Text(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column("zoom_participants", "email")
    # ### end Alembic commands ###
