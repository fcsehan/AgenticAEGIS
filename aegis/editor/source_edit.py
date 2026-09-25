"""Source-preserving edits of complete top-level MELD assertions."""

from __future__ import annotations


def assertion_spans(text: str) -> list[tuple[int, int]]:
    spans = []
    depth = 0
    start = 0
    quoted = False
    escaped = False
    comment = False
    for index, char in enumerate(text):
        if comment:
            comment = char != "\n"
            continue
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == ";":
            comment = True
        elif char == '"':
            quoted = True
        elif char == "(":
            if depth == 0:
                start = index
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise ValueError("Unbalanced MELD source")
            if depth == 0:
                spans.append((start, index + 1))
    if depth or quoted:
        raise ValueError("Incomplete MELD source")
    return spans


def replace_assertion(text: str, index: int, replacement: str) -> str:
    spans = assertion_spans(text)
    if index < 1 or index > len(spans):
        raise ValueError("Source assertion no longer exists")
    start, end = spans[index - 1]
    return text[:start] + replacement + text[end:]


def rename_symbol(text: str, old: str, new: str) -> str:
    """Rename atoms while preserving quoted literals, comments and whitespace."""
    parts = []
    index = 0
    while index < len(text):
        start = index
        char = text[index]
        if char == ";":
            end = text.find("\n", index)
            index = len(text) if end < 0 else end
        elif char == '"':
            index += 1
            while index < len(text):
                if text[index] == "\\":
                    index += 2
                elif text[index] == '"':
                    index += 1
                    break
                else:
                    index += 1
        elif char.isspace() or char in "()":
            index += 1
        else:
            while index < len(text) and not text[index].isspace() and text[index] not in '();"':
                index += 1
            atom = text[start:index]
            parts.append(new if atom == old else atom)
            continue
        parts.append(text[start:index])
    return "".join(parts)
