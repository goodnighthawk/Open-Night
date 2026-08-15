# Open Night v0.7.3

This release adds a moderated player-feedback pipeline over the v0.7.2 map and
multiplayer movement build.

## Player reporting

- `/bug description`, `/mapfeedback description`, and F10 keep a private local
  CSV/PNG recovery copy and submit a report to the Railway server.
- The server stores reports in MySQL with status `pending`.
- Screenshots are limited to 1.5 MB, decoded and re-encoded as bounded PNGs,
  and stripped of metadata before storage.
- Reporter account/network identifiers are salted; raw phone/account values are
  not exposed to reviewers or exported feedback.
- Submissions are limited to one accepted report per account every 45 seconds,
  a network-source cooldown, and ten reports per login session.

## Human approval

- `REVIEW_BUG_REPORTS.bat` connects through a secret
  `PYMMO_BUG_ADMIN_TOKEN` stored in Railway.
- Reviewers inspect the report and screenshot, then type the exact
  `APPROVE <id>` or `REJECT <id>` confirmation.
- Only approved reports are exported to `feedback/approved/` for GitHub and
  ChatGPT. Spreadsheet-formula prefixes are neutralized during CSV export.
- Player text is explicitly untrusted evidence and can never directly trigger
  code changes or override development rules.

## Compatibility

- The accepted pass-17 map and v0.7.2 movement/pose behavior are unchanged.
- Deploying patch ID `open-night-v0.7.3` resets prototype accounts/inventory
  once under the current development policy; the moderation queue is retained.
