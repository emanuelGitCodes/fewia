import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILES = ["backend/Dockerfile", "frontend/Dockerfile"]
DIGEST = re.compile(r"@sha256:[0-9a-f]{64}$")


def _image_refs(text: str) -> list[str]:
    stages = {
        m.group(1) for m in re.finditer(r"^FROM\s+\S+\s+AS\s+(\S+)", text, re.I | re.M)
    }
    refs = []
    for line in text.splitlines():
        from_match = re.match(r"\s*FROM\s+(?:--\S+\s+)*(\S+)", line, re.I)
        if from_match:
            ref = from_match.group(1)
            if ref not in stages and ref.lower() != "scratch":
                refs.append(ref)
            continue
        copy_match = re.match(r"\s*COPY\s+.*?--from=(\S+)", line, re.I)
        if copy_match:
            ref = copy_match.group(1)
            if ref not in stages and ("/" in ref or ":" in ref):
                refs.append(ref)
    return refs


def _unpinned_refs(text: str) -> list[str]:
    return [ref for ref in _image_refs(text) if not DIGEST.search(ref)]


def test_dockerfile_images_pinned_by_digest() -> None:
    for name in DOCKERFILES:
        text = (ROOT / name).read_text()
        assert _image_refs(text), f"no image references found in {name}"
        unpinned = _unpinned_refs(text)
        assert not unpinned, f"{name}: not pinned by digest: {unpinned}"


def test_stage_reference_is_accepted() -> None:
    text = "FROM a:1@sha256:" + "0" * 64 + " AS build\nCOPY --from=build /x /y\n"
    assert len(_image_refs(text)) == 1
    assert _unpinned_refs(text) == []


def test_unpinned_image_is_reported() -> None:
    assert _unpinned_refs("FROM a:1\n") == ["a:1"]
