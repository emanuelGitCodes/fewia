import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / ".github/scripts/validate-compose.sh"
MOUNTS = {
    "FEWIA_LOCAL_ADMIN_PASSWORD_FILE": "admin-password",
    "FEWIA_LOCAL_RUNTIME_PASSWORD_FILE": "runtime-password",
    "FEWIA_LOCAL_PAIRING_KEY_FILE": "pairing-key",
    "FEWIA_KROGER_CLIENT_ID_FILE": "kroger-client-id",
    "FEWIA_KROGER_SECRET_FILE": "kroger-secret",
    "FEWIA_KROGER_TOKEN_KEY_FILE": "kroger-token-key",
}


@pytest.mark.parametrize("fail_call", [0, 1, 2, 3])
def test_compose_fixtures_are_private_isolated_and_removed(
    tmp_path: Path, fail_call: int
) -> None:
    checkout = tmp_path / "checkout"
    script = checkout / ".github/scripts/validate-compose.sh"
    script.parent.mkdir(parents=True)
    script.write_text(HELPER.read_text())
    script.chmod(0o600)
    for name in ("compose.yaml", "compose.kroger.yaml", "compose.tools.yaml"):
        (checkout / name).write_text((ROOT / name).read_text())
    dotenv = "COMPOSE_FILE=/hostile/compose.yaml\nFEWIA_HOST_UID=hostile\n"
    (checkout / ".env").write_text(dotenv)
    (checkout / "compose.override.yaml").write_text("invalid: [\n")
    snapshot = tmp_path / "calls.jsonl"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        f"#!{sys.executable}\n"
        f"SNAPSHOT = {str(snapshot)!r}\n"
        f"MOUNTS = {MOUNTS!r}\n"
        f"FAIL_CALL = {fail_call}\n"
        + """
import json
import os
import re
import stat
import sys
from pathlib import Path

args = sys.argv[1:]
assert args[:2] == ['compose', '--env-file']
assert args[-2:] == ['config', '--quiet']
assert set(os.environ) <= {
    'PATH', 'HOME', 'LC_CTYPE', '__CF_USER_TEXT_ENCODING'
}
env_file = Path(args[2])
assert env_file.is_absolute()
assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
fixtures = env_file.parent
assert stat.S_IMODE(fixtures.stat().st_mode) == 0o700
values = dict(line.split('=', 1) for line in env_file.read_text().splitlines())
assert set(values) == set(MOUNTS) | {
    'FEWIA_HOST_UID', 'FEWIA_HOST_GID', 'FEWIA_OPENAI_API_KEY'
}
assert re.fullmatch(r'[0-9]+', values['FEWIA_HOST_UID'])
assert re.fullmatch(r'[0-9]+', values['FEWIA_HOST_GID'])
assert values['FEWIA_HOST_UID'] == str(os.getuid())
assert values['FEWIA_HOST_GID'] == str(os.getgid())
assert values['FEWIA_OPENAI_API_KEY'] == 'compose-validation-only'
for variable, filename in MOUNTS.items():
    path = Path(values[variable])
    assert path == fixtures / filename
    assert path.is_file() and not path.is_symlink()
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.read_text() == 'compose-validation-only\\n'
assert {path.name for path in fixtures.iterdir()} == (
    set(MOUNTS.values()) | {'compose.env'}
)
files = args[3:-2]
assert files in (
    ['-f', 'compose.yaml'],
    ['-f', 'compose.yaml', '-f', 'compose.kroger.yaml'],
    ['-f', 'compose.yaml', '-f', 'compose.tools.yaml'],
)
assert Path('compose.yaml').is_file()
record = {'fixtures': str(fixtures), 'files': files, 'cwd': str(Path.cwd())}
snapshot = Path(SNAPSHOT)
count = len(snapshot.read_text().splitlines()) if snapshot.exists() else 0
with snapshot.open('a') as stream:
    stream.write(json.dumps(record) + '\\n')
if count + 1 == FAIL_CALL:
    sys.exit(23)
"""
    )
    docker.chmod(0o700)
    env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.defpath}",
        "HOME": str(tmp_path),
        "COMPOSE_FILE": "/hostile/compose.yaml",
        "COMPOSE_ENV_FILES": "/hostile/.env",
        "COMPOSE_PROJECT_NAME": "hostile",
        "DOCKER_HOST": "tcp://hostile.invalid:2375",
        "DOCKER_CONTEXT": "hostile",
        "API_HOST_PORT": "invalid",
        "FEWIA_OPENAI_API_KEY": "inherited-synthetic-placeholder",
        "FEWIA_HOST_UID": "invalid",
        "FEWIA_HOST_GID": "invalid",
        **{name: "/hostile/mount" for name in MOUNTS},
    }
    done = subprocess.run(
        ["bash", str(script)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert done.returncode == (23 if fail_call else 0), done.stderr
    assert done.stdout == ""
    assert done.stderr == ""
    calls = [json.loads(line) for line in snapshot.read_text().splitlines()]
    expected_files = [
        ["-f", "compose.yaml"],
        ["-f", "compose.yaml", "-f", "compose.kroger.yaml"],
        ["-f", "compose.yaml", "-f", "compose.tools.yaml"],
    ]
    assert [row["files"] for row in calls] == expected_files[: fail_call or 3]
    assert {row["cwd"] for row in calls} == {str(checkout.resolve())}
    assert len({row["fixtures"] for row in calls}) == 1
    assert all(not Path(row["fixtures"]).exists() for row in calls)
    assert (checkout / ".env").read_text() == dotenv
    assert not (checkout / ".fewia-state").exists()


def test_compose_required_mounts_match_fixture_contract() -> None:
    required: set[str] = set()
    for name in ("compose.yaml", "compose.kroger.yaml"):
        required.update(re.findall(r"\$\{([A-Z_]+):\?", (ROOT / name).read_text()))
    assert required == set(MOUNTS) | {"FEWIA_HOST_UID", "FEWIA_HOST_GID"}


def test_ci_uses_shared_compose_helper_and_tcp_database_health() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "run: bash .github/scripts/validate-compose.sh" in workflow
    assert "/tmp/fewia-ci" not in workflow
    assert "pg_isready -h 127.0.0.1 -U fewia -d fewia_eval -p 5432" in workflow
