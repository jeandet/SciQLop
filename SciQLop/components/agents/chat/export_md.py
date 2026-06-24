"""Serialize a chat transcript (list of ChatMessage) to Markdown.

Pure rendering of the in-memory message/block model, so a saved .md mirrors the
in-app transcript: role headings, assistant text as-is, thinking as a blockquote,
images as links, and (when present) tool activity as a collapsible ``<details>``
block that renders nicely on GitHub and other Markdown viewers.
"""
from __future__ import annotations

from typing import Any, List

from .view import ChatMessage, ImageBlock, TextBlock, ThinkingBlock

_ROLE = {"user": "You", "assistant": "Claude", "error": "Error"}


def _block_md(block: Any) -> List[str]:
    if isinstance(block, ThinkingBlock):
        text = (block.text or "").strip()
        if not text:
            return []
        return ["> " + line for line in text.splitlines()]
    if isinstance(block, TextBlock):
        return [(block.text or "").rstrip()]
    if isinstance(block, ImageBlock):
        return [f"![image]({block.path})"]
    # Tool-activity blocks (added with the activity feature) expose tool_name /
    # steps; render them collapsed so the export stays readable.
    steps = getattr(block, "steps", None)
    if steps is not None:
        out = ["<details>", f"<summary>🔧 {len(steps)} steps</summary>", ""]
        out += [f"- {s}" for s in steps]
        out += ["", "</details>"]
        return out
    return []


def transcript_to_markdown(messages: List[ChatMessage], title: str = "SciQLop chat") -> str:
    lines: List[str] = [f"# {title}", ""]
    for msg in messages:
        role = _ROLE.get(getattr(msg, "role", ""), getattr(msg, "role", "?"))
        lines.append(f"## {role}")
        lines.append("")
        for block in getattr(msg, "blocks", []) or []:
            rendered = _block_md(block)
            if rendered:
                lines.extend(rendered)
                lines.append("")
    return "\n".join(lines).rstrip() + "\n"
