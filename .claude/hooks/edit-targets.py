"""Print the files that one edit tool call writes, as a JSON array.

Read the hook input on stdin. A Claude Code or Grok edit names one file in
`tool_input.file_path` or `tool_input.notebook_path`, relative to the
project root. A Codex `apply_patch` call holds a patch in
`tool_input.command`; its paths are relative to the session `cwd`.

Each item is {"path", "op", "appends"}. `op` is the tool name, or `add`,
`update`, `delete`, `move_from`, or `move_to` for a patch. `appends` is
true for an update that only adds lines after the end of the file.

With `--relative ROOT`, print only the paths inside a checkout of the
repository instead. The checkouts are ROOT and every worktree that
`git worktree list` reports. Each path is resolved with symbolic links and
made relative to the deepest checkout that holds it.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

PATCH_OPS = (
    ("*** Add File: ", "add"),
    ("*** Update File: ", "update"),
    ("*** Delete File: ", "delete"),
)


def targets(data: dict, root: str) -> list[dict]:
    tool_input = data.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("notebook_path")
    if path:
        return [
            {
                "path": os.path.join(root, path),
                "op": data.get("tool_name"),
                "appends": False,
            }
        ]
    patch = tool_input.get("command")
    if data.get("tool_name") != "apply_patch" or not isinstance(patch, str):
        return []
    base = data.get("cwd") or root
    found: list[dict] = []
    bodies: list[list[str]] = []
    for line in patch.splitlines():
        for prefix, op in PATCH_OPS:
            if line.startswith(prefix):
                found.append(
                    {"path": os.path.join(base, line[len(prefix) :]), "op": op}
                )
                bodies.append([])
                break
        else:
            if found and line.startswith("*** Move to: "):
                found[-1]["op"] = "move_from"
                found.append({"path": os.path.join(base, line[13:]), "op": "move_to"})
                bodies.append([])
            elif found:
                bodies[-1].append(line)
    for target, body in zip(found, bodies):
        target["appends"] = target["op"] == "update" and appends(target["path"], body)
    return found


def appends(path: str, body: list[str]) -> bool:
    """Return true when every added line follows all context lines, and the
    context lines are the last lines of the file and match nowhere else."""
    context: list[str] = []
    added = False
    for line in body:
        if line.startswith("-") or (line.startswith(" ") and added):
            return False
        if line.startswith("+"):
            added = True
        elif line.startswith(" "):
            context.append(line[1:])
    try:
        with open(path, encoding="utf-8") as handle:
            existing = handle.read().splitlines()
    except OSError:
        return False
    if not existing:
        return True
    n = len(context)
    matches = [
        i for i in range(len(existing) - n + 1) if existing[i : i + n] == context
    ]
    return n > 0 and matches == [len(existing) - n]


def checkouts(root: str) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "-C", root, "worktree", "list", "--porcelain", "-z"],
            capture_output=True,
            text=True,
        )
    except OSError:
        return [root]
    listing = result.stdout if result.returncode == 0 else ""
    return [root] + [f[9:] for f in listing.split("\0") if f.startswith("worktree ")]


def relative(paths: list[str], root: str) -> list[str]:
    tops = [os.path.realpath(top) for top in checkouts(root)]
    found = []
    for path in paths:
        path = os.path.realpath(path)
        best = max(
            (t for t in tops if path.startswith(t + os.sep)), key=len, default=""
        )
        if best:
            found.append(os.path.relpath(path, best))
    return found


def main() -> None:
    data = json.load(sys.stdin)
    if len(sys.argv) == 3 and sys.argv[1] == "--relative":
        root = sys.argv[2]
        paths = [t["path"] for t in targets(data, root)]
        print(json.dumps(relative(paths, root)))
        return
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    print(json.dumps(targets(data, root)))


if __name__ == "__main__":
    main()
