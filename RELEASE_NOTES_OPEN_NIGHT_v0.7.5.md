# Open Night v0.7.5

This small usability patch is built directly over v0.7.4.

## Text editing

- Ctrl+A selects the complete active text entry.
- Ctrl+C copies, Ctrl+X cuts, and Ctrl+V pastes.
- Supported fields: launcher phone/name/server address, chat and SMS composition, and the F10 issue-report note.
- Browser builds request clipboard access through the browser API and keep an in-game fallback if permission is unavailable.

## Bug-report reminder

Opening chat now displays a dedicated highlighted reminder:

`/bug describe what went wrong — saves a screenshot to the human-approval queue`

The existing moderated report workflow is unchanged: player reports cannot automatically become implementation work.

## Compatibility

The client and server version are now 0.7.5. Upgrade the Railway service and every client together.
