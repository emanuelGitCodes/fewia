#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Word:
    text: str
    literal: bool
    plain: bool


def words(command: str) -> list[Word | str]:
    tokens: list[Word | str] = []
    value: list[str] = []
    active = False
    literal = plain = True
    quote = ""
    index = 0

    def finish() -> None:
        nonlocal active, literal, plain
        if active:
            tokens.append(Word("".join(value), literal, plain))
        value.clear()
        active = False
        literal = plain = True

    while index < len(command):
        if len(tokens) > 8192:
            raise ValueError
        char = command[index]
        if char == "\\" and quote != "'":
            if index + 1 == len(command):
                raise ValueError
            following = command[index + 1]
            if not quote or following in '$`"\\\n':
                if following != "\n":
                    value.append(following)
                    active = True
                plain = False
                index += 2
                continue
        if quote:
            if char == quote:
                quote = ""
            else:
                value.append(char)
                if quote == '"' and char in "$`":
                    literal = False
        elif char in "'\"":
            quote = char
            active = True
            plain = False
        elif char == "#" and not active:
            while index < len(command) and command[index] != "\n":
                index += 1
            continue
        elif char in " \t\r\n;&|()<>":
            finish()
            if char not in " \t\r":
                operator = char
                for candidate in ("&>>", "<<<", ">>", "<<", ">&", "<&", "<>", "&>"):
                    if command.startswith(candidate, index):
                        operator = candidate
                        break
                tokens.append(operator)
                index += len(operator) - 1
        else:
            active = True
            value.append(char)
            if char in "$`*?[{}~":
                literal = False
        index += 1
    if quote:
        raise ValueError
    finish()
    return tokens


def assignment(word: Word) -> bool:
    name, separator, _ = word.text.partition("=")
    return bool(separator and name.isascii() and name.isidentifier())


def invocation(segment: list[Word]) -> tuple[list[Word], bool, bool]:
    index = 0
    conventional = True
    skip_gitleaks = False
    while index < len(segment):
        word = segment[index]
        if assignment(word):
            name, _, value = word.text.partition("=")
            skip_gitleaks |= name == "SKIP" and "gitleaks" in value.split(",")
        elif word.plain and word.text in {
            "!",
            "{",
            "}",
            "if",
            "then",
            "elif",
            "else",
            "do",
            "while",
            "until",
        }:
            pass
        elif word.literal and word.text in {"env", "command", "exec", "time", "nohup"}:
            wrapper = word.text
            index += 1
            while index < len(segment) and segment[index].text.startswith("-"):
                option = segment[index].text
                index += 1
                if option == "--":
                    break
                if (
                    wrapper == "env" and option in {"-u", "--unset", "-C", "--chdir"}
                ) or (wrapper == "exec" and option == "-a"):
                    index += 1
            conventional = False
            continue
        else:
            break
        conventional = False
        index += 1
    return segment[index:], conventional, skip_gitleaks


def git_command(arguments: list[Word]) -> tuple[int, bool]:
    index = 1
    while index < len(arguments):
        word = arguments[index]
        if not word.literal:
            return index, False
        option = word.text
        if option in {"-C", "-c", "--git-dir", "--work-tree"}:
            if index + 1 >= len(arguments) or not arguments[index + 1].literal:
                return index, False
            index += 2
        elif option in {"--no-pager", "--paginate", "--bare"} or option.startswith(
            ("--git-dir=", "--work-tree=", "-C", "-c")
        ):
            index += 1
        elif option.startswith("-"):
            # Unknown global options have no known argument count.
            for candidate in range(index + 1, len(arguments)):
                if not arguments[candidate].literal or arguments[candidate].text in {
                    "push",
                    "merge",
                    "commit",
                }:
                    return candidate, False
            return len(arguments), False
        else:
            return index, True
    return index, True


def classify_segment(segment: list[Word | str]) -> str:
    arguments: list[Word] = []
    redirected = False
    skip_target = False
    for token in segment:
        if isinstance(token, str):
            if arguments and arguments[-1].plain and arguments[-1].text.isdecimal():
                arguments.pop()
            redirected = skip_target = True
        elif skip_target:
            skip_target = False
        else:
            arguments.append(token)
    arguments, conventional, skip_gitleaks = invocation(arguments)
    if (
        not arguments
        or not arguments[0].literal
        or arguments[0].text.rsplit("/", 1)[-1].casefold() != "git"
    ):
        return "allow"
    if skip_gitleaks:
        return "gitleaks"
    index, familiar = git_command(arguments)
    if index >= len(arguments):
        return "allow"
    word = arguments[index]
    if not word.literal:
        return "ambiguous"
    subcommand = word.text
    if subcommand not in {"push", "merge", "commit"}:
        return "allow"
    tail = arguments[index + 1 :]
    for word in tail:
        option = word.text.partition("=")[0]
        if (
            option == "--no-verify"
            or (option.startswith("--no-v") and "--no-verify".startswith(option))
            or (
                subcommand == "commit"
                and option.startswith("-")
                and not option.startswith("--")
                and "n" in option
            )
        ):
            return "gitleaks"
    if subcommand == "commit":
        if not familiar or redirected or any(not word.literal for word in tail):
            return "ambiguous"
        return "allow"
    if subcommand == "push":
        for word in tail:
            argument = word.text
            option = argument.partition("=")[0]
            if (
                (
                    option.startswith("--f")
                    and ("--force".startswith(option) or option.startswith("--force"))
                )
                or (
                    option.startswith("-")
                    and not option.startswith("--")
                    and "f" in option
                )
                or argument.startswith("+")
            ):
                return "force"
            broad_options = {
                "--tags",
                "--all",
                "--delete",
                "--mirror",
                "--prune",
                "--follow-tags",
            }
            if (
                option == "-d"
                or (
                    option.startswith("--")
                    and len(option) > 2
                    and any(flag.startswith(option) for flag in broad_options)
                )
                or argument == ":"
                or "*" in argument
            ):
                return "broad"
            if not argument.startswith("-") and argument.rsplit(":", 1)[-1] in {
                "main",
                "refs/heads/main",
            }:
                return "main"
    if not familiar or redirected or any(not word.literal for word in tail):
        return "ambiguous"
    if not conventional or not arguments[0].plain or arguments[0].text != "git":
        return "ambiguous"
    return "external"


def classify(command: str) -> str:
    result = "allow"
    segment: list[Word | str] = []
    for token in [*words(command), ";"]:
        if isinstance(token, str) and token in {";", "&", "|", "(", ")", "\n"}:
            decision = classify_segment(segment)
            segment.clear()
            if decision not in {"allow", "external"}:
                return decision
            if decision == "external":
                result = decision
        else:
            segment.append(token)
    return result


def main() -> None:
    try:
        raw = sys.stdin.buffer.read(1048577)
        if len(raw) > 1048576:
            raise ValueError
        payload = json.loads(raw)
        command = payload["tool_input"]["command"]
        if not isinstance(command, str) or "\0" in command:
            raise ValueError
        result = classify(command)
    except (KeyError, TypeError, ValueError, UnicodeError):
        result = "ambiguous"
    print(result)


if __name__ == "__main__":
    main()
