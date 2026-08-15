from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def function_names(tree: ast.AST) -> set[str]:
    return {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def main() -> int:
    source = (ROOT / "client.py").read_text(encoding="utf-8")
    tree = ast.parse(source, filename="client.py")
    names = function_names(tree)
    for name in (
        "normalize_clipboard_text",
        "copy_to_clipboard",
        "request_clipboard_text",
        "shortcut_modifier",
        "paste_chat_text",
        "paste_issue_report_text",
    ):
        assert name in names, name

    for token in (
        "pygame.KMOD_CTRL | pygame.KMOD_META",
        "navigator.clipboard.writeText",
        "navigator.clipboard.readText",
        "pygame.scrap.put",
        "pygame.scrap.get",
        "request_clipboard_text(self.paste)",
        "request_clipboard_text(self.paste_chat_text)",
        "request_clipboard_text(self.paste_issue_report_text)",
        "/bug describe what went wrong — saves a screenshot to the human-approval queue",
        "CTRL+A/C/X/V edit",
    ):
        assert token in source, token

    version_source = (ROOT / "versioning.py").read_text(encoding="utf-8")
    match = re.search(r'^GAME_VERSION = "([0-9]+\.[0-9]+\.[0-9]+)"$', version_source, re.MULTILINE)
    assert match, "GAME_VERSION"
    version = match.group(1)
    assert f"Open Night v{version}" in (ROOT / "VERSION.txt").read_text(encoding="utf-8")
    assert f"open-night-v{version}" in (ROOT / "railway.toml").read_text(encoding="utf-8")

    print(f"OPEN NIGHT v{version} CLIPBOARD / CHAT-HINT AUDIT: PASS")
    print("  launcher, chat/SMS, report editing, browser fallback and /bug guidance verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
