from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STRIP_ROOT_ESTIMATE_SQL = """
UPDATE jobs
SET result = (result::jsonb - 'supermarket_estimate')::json
WHERE jsonb_typeof(result::jsonb) = 'object'
  AND jsonb_exists(result::jsonb, 'supermarket_estimate')
"""


def upgrade() -> None:
    op.execute(sa.text(STRIP_ROOT_ESTIMATE_SQL))


def downgrade() -> None:
    raise RuntimeError("Forward-only migration; downgrade is not supported.")
