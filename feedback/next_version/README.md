# Next-version player feedback

While playing, press Enter and submit:

`/bug describe what went wrong and where`

Open Night creates/appends the description and gameplay context in `next_version_feedback.csv` and saves a PNG in `screenshots/`. F10 reports are mirrored here too. The generated CSV and PNG files are intentionally not part of a clean checkout, so they do not prevent the launcher from fast-forwarding to a new game version.

These files stay on the player's computer. When this game is running from a cloned GitHub repository, GitHub Desktop will show new feedback rows and screenshots as local changes. Review them before committing and pushing; that deliberate push is what makes the reports available for the next development pass.

Do not record passwords, phone numbers, private chat, or other sensitive information in a bug description or screenshot.
