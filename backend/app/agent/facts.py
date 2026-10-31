from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Fact:
    source_tool: str
    path: str
    value: int


def _walk(source_tool: str, node: object, path: str, out: list[Fact]) -> None:
    if isinstance(node, dict):
        for key, child in node.items():
            _walk(source_tool, child, f"{path}.{key}" if path else str(key), out)
    elif isinstance(node, list):
        for index, child in enumerate(node):
            _walk(source_tool, child, f"{path}[{index}]", out)
    elif type(node) is int:
        out.append(Fact(source_tool, path, node))


def collect_facts(source_tool: str, payload: object) -> list[Fact]:
    """List every int leaf of a tool payload, depth-first in key order."""
    facts: list[Fact] = []
    _walk(source_tool, payload, "", facts)
    return facts
