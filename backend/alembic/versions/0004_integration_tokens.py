"""Encrypted OAuth token storage.

Adds the refresh token, its expiry and a last-error field. Access and refresh
tokens are Fernet-encrypted before they are written, so these columns hold
ciphertext only.
"""
from alembic import op
import sqlalchemy as sa
import app.core.database

revision = "0004_integration_tokens"
down_revision = "0003_signal_detail"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("integrations", sa.Column("encrypted_refresh", sa.Text(), nullable=True))
    op.add_column("integrations",
                  sa.Column("token_expires_at", app.core.database.UTCDateTime(), nullable=True))
    op.add_column("integrations",
                  sa.Column("last_error", sa.String(), nullable=True, server_default=""))


def downgrade():
    op.drop_column("integrations", "last_error")
    op.drop_column("integrations", "token_expires_at")
    op.drop_column("integrations", "encrypted_refresh")
