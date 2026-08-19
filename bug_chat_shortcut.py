from __future__ import annotations

"""v1.1 bug-report input shortcut.

F10 is deliberately a chat shortcut now: it focuses the normal chat input and
prefills ``/bug `` so the player only has to type the description and press
Enter.  The existing ``/bug`` submit path remains the single authority for
capturing the screenshot and saving/queueing the report.
"""

import time

import pygame

import client as game_client


_INSTALLED = False
_ORIGINAL_HANDLE_ISSUE_REPORT_KEY = None


def install() -> None:
    """Replace the legacy F10 modal entry point with the normal /bug chat path."""
    global _INSTALLED, _ORIGINAL_HANDLE_ISSUE_REPORT_KEY
    if _INSTALLED:
        return

    original = game_client.Game.handle_issue_report_key
    _ORIGINAL_HANDLE_ISSUE_REPORT_KEY = original

    def handle_issue_report_key(self, event: pygame.event.Event) -> bool:
        if event.key == pygame.K_F10:
            # If the legacy reporter happened to be open, retire it completely so
            # there is only one visible bug-report workflow.
            self.issue_report_open = False
            self.issue_report_note = ""
            self.issue_report_select_all = False
            self.issue_report_snapshot = None

            # Use the established chat command pipeline.  submit_chat() already
            # owns screenshot capture, metadata, local backup and server queueing.
            self.chat_active = True
            self.chat_text = "/bug "
            self.chat_select_all = False
            self.sms_open = False
            self.notice = "Describe the bug, then press Enter"
            self.notice_until = time.monotonic() + 3.0
            return True

        return original(self, event)

    game_client.Game.handle_issue_report_key = handle_issue_report_key
    _INSTALLED = True
