"""aslpp to sign cafe

Revision ID: beec26d674fd
Revises: f4eff610ab27
Create Date: 2022-01-15 01:13:57.549431

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

import bot

# revision identifiers, used by Alembic.
revision = "beec26d674fd"
down_revision = "f4eff610ab27"
branch_labels = None
depends_on = None


def upgrade():
    op.rename_table("aslpp_intros", "sign_cafe_intros")
    op.rename_table("aslpp_members", "sign_cafe_members")

    op.execute(
        "ALTER INDEX ix_aslpp_intros_user_id RENAME TO ix_sign_cafe_intros_user_id"
    )
    op.execute("ALTER INDEX aslpp_intros_pkey RENAME TO sign_cafe_intros_pkey")
    op.execute("ALTER INDEX aslpp_members_pkey RENAME TO sign_cafe_members_pkey")


def downgrade():
    op.rename_table("sign_cafe_intros", "aslpp_intros")
    op.rename_table("sign_cafe_members", "aslpp_members")

    op.execute(
        "ALTER INDEX ix_sign_cafe_intros_user_id RENAME TO ix_aslpp_intros_user_id"
    )
    op.execute("ALTER INDEX sign_cafe_intros_pkey RENAME TO aslpp_intros_pkey")
    op.execute("ALTER INDEX sign_cafe_members_pkey RENAME TO aslpp_members_pkey")
