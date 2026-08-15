# Next-version development tasks

This folder contains developer-authored planning only. Internet player reports
no longer write here directly.

While playing, `/bug description`, `/mapfeedback description`, and F10 keep a
private local recovery copy and submit to the Railway MySQL queue as `pending`.
Run `REVIEW_BUG_REPORTS.bat` to inspect and explicitly approve or reject each
report. Only approved reports are exported to `feedback/approved/`, which is the
sole player-feedback location development agents may use.

Do not record passwords, phone numbers, private chat, or other sensitive
information in a bug description or screenshot.
