"""Exercise publisher row locking against isolated PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.job_models import JobOutbox
from app.services.job_submission import create_job
from app.services.outbox_publisher import publish_pending

pytest_plugins = ["test_job_submission_postgres"]


def test_publishers_skip_each_others_locked_rows(
    postgres_user: tuple[Engine, int],
) -> None:
    engine, user_id = postgres_user
    factory = sessionmaker(engine)
    with factory.begin() as session:
        jobs = [
            create_job(session, user_id, "agent", f"publisher-{i}", {})[0]
            for i in range(2)
        ]
        ids = {job.id for job in jobs}
    rendezvous = Barrier(2)
    sent: list[str] = []

    class Sender:
        def send(self, kind: str, job_id: str) -> None:
            assert kind == "agent"
            assert job_id in ids
            rendezvous.wait(timeout=10)
            sent.append(job_id)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(publish_pending, factory, Sender(), 1) for _ in range(2)
        ]
        assert [future.result(timeout=20) for future in futures] == [1, 1]
    assert len(sent) == 2
    assert set(sent) == ids
    with Session(engine) as session:
        rows = session.scalars(select(JobOutbox).where(JobOutbox.job_id.in_(ids))).all()
        assert len(rows) == 2
        assert all(row.published_at is not None for row in rows)
