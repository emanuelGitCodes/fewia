"""Reserve user IDs before generated identity values."""

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            user_sequence regclass;
            sequence_value bigint;
        BEGIN
            LOCK TABLE public.users IN SHARE ROW EXCLUSIVE MODE;
            user_sequence := pg_get_serial_sequence('public.users', 'id')::regclass;
            IF user_sequence IS NULL THEN
                RAISE EXCEPTION 'users identity sequence is missing';
            END IF;
            EXECUTE format('SELECT last_value FROM %s', user_sequence)
                INTO sequence_value;
            PERFORM setval(
                user_sequence,
                GREATEST(1, (SELECT MAX(id) FROM public.users), sequence_value),
                true
            );
        END;
        $$;
        """
    )


def downgrade() -> None:
    raise RuntimeError("Forward-only migration; downgrade is not supported.")
