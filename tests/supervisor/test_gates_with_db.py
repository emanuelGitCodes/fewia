import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / ".github/scripts/gates-with-db.sh"
DB_KEYS = (
    "DATABASE_URL",
    "FEWIA_JOB_TEST_DATABASE_URL",
    "FEWIA_EVALUATION_DATABASE_URL",
)


@pytest.mark.parametrize(
    ("failure", "returncode", "uv_count"),
    [
        ("", 0, 3),
        ("startup", 1, 0),
        ("timeout", 1, 0),
        ("final_probe", 1, 0),
        ("upgrade", 23, 1),
        ("check", 23, 2),
        ("gates", 23, 3),
        ("SIGHUP", 129, 3),
        ("SIGINT", 130, 3),
        ("SIGTERM", 143, 3),
    ],
)
def test_database_helper_sequence_and_cleanup(
    tmp_path: Path, failure: str, returncode: int, uv_count: int
) -> None:
    checkout = tmp_path / "checkout"
    script = checkout / ".github/scripts/gates-with-db.sh"
    script.parent.mkdir(parents=True)
    script.write_text(HELPER.read_text())
    (checkout / "backend").mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    snapshot = tmp_path / "calls.jsonl"
    stub = (
        f"#!{sys.executable}\n"
        + """
import json
import os
import signal
import sys
from pathlib import Path

tool = Path(sys.argv[0]).name
args = sys.argv[1:]
if tool == 'python3':
    print('15432')
    sys.exit(0)
if tool == 'sleep':
    sys.exit(0)
snapshot = Path(os.environ['SNAPSHOT'])
rows = (
    [json.loads(line) for line in snapshot.read_text().splitlines()]
    if snapshot.exists() else []
)
keys = ('DATABASE_URL', 'FEWIA_JOB_TEST_DATABASE_URL',
        'FEWIA_EVALUATION_DATABASE_URL', 'FEWIA_REQUIRE_DB')
row = {'tool': tool, 'args': args, 'cwd': str(Path.cwd()),
       'env': {key: os.environ.get(key) for key in keys}}
with snapshot.open('a') as stream:
    stream.write(json.dumps(row) + '\\n')
failure = os.environ['FAILURE']
if tool == 'docker':
    if args[0] == 'run' and failure == 'startup':
        print('synthetic Docker diagnostics', file=sys.stderr)
        sys.exit(23)
    if args[0] == 'exec':
        probes = sum(row['args'][0] == 'exec' for row in rows)
        if failure == 'timeout' or (failure == 'final_probe' and probes):
            print('synthetic probe diagnostics', file=sys.stderr)
            sys.exit(23)
if tool == 'uv':
    stage = args[2] if args[:2] == ['run', 'alembic'] else 'gates'
    if stage == failure:
        sys.exit(23)
    if stage == 'gates' and failure.startswith('SIG'):
        os.kill(os.getppid(), getattr(signal, failure))
"""
    )
    for name in ("docker", "uv", "python3", "sleep"):
        executable = bin_dir / name
        executable.write_text(stub)
        executable.chmod(0o700)
    done = subprocess.run(
        ["bash", str(script), "--base", "topic with spaces"],
        cwd=tmp_path,
        env={
            "PATH": f"{bin_dir}{os.pathsep}{os.defpath}",
            "HOME": str(tmp_path),
            "SNAPSHOT": str(snapshot),
            "FAILURE": failure,
        },
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert done.returncode == returncode, done.stderr
    assert done.stdout == ""
    expected_error = {
        "startup": "Database container startup failed.\n",
        "timeout": "Database readiness failed.\n",
        "final_probe": "Database readiness failed.\n",
    }
    assert done.stderr == expected_error.get(failure, "")
    rows = [json.loads(line) for line in snapshot.read_text().splitlines()]
    start = rows[0]["args"]
    assert start[:3] == ["run", "-d", "--name"]
    name = start[3]
    assert start[4:] == [
        "-e",
        "POSTGRES_USER=fewia",
        "-e",
        "POSTGRES_PASSWORD=fewia",
        "-e",
        "POSTGRES_DB=fewia_eval",
        "-p",
        "127.0.0.1:15432:5432",
        "postgres:16",
    ]
    assert rows[-1]["args"] == ["rm", "-f", name]
    probes = [row for row in rows if row["args"][0] == "exec"]
    expected_probes = {"startup": 0, "timeout": 31}.get(failure, 2)
    assert len(probes) == expected_probes
    assert [row["tool"] for row in rows] == (
        ["docker"] * (1 + expected_probes) + ["uv"] * uv_count + ["docker"]
    )
    for row in probes:
        assert row["args"] == [
            "exec",
            name,
            "pg_isready",
            "-h",
            "127.0.0.1",
            "-p",
            "5432",
            "-U",
            "fewia",
            "-d",
            "fewia_eval",
        ]
    uv_calls = [row for row in rows if row["tool"] == "uv"]
    assert [row["args"] for row in uv_calls] == [
        ["run", "alembic", "upgrade", "head"],
        ["run", "alembic", "check"],
        [
            "run",
            "--project",
            "backend",
            "python",
            "-m",
            "dev_supervisor.gates",
            "--cwd",
            str(checkout),
            "--base",
            "topic with spaces",
        ],
    ][:uv_count]
    url = "postgresql+psycopg://fewia:fewia@127.0.0.1:15432/fewia_eval"
    for row in uv_calls:
        assert row["env"] == {
            **dict.fromkeys(DB_KEYS, url),
            "FEWIA_REQUIRE_DB": "1",
        }
        expected_cwd = checkout / "backend" if "alembic" in row["args"] else checkout
        assert row["cwd"] == str(expected_cwd)
