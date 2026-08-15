# Open Night v0.8.1 — Railway internet server with MySQL

The desktop client automatically checks the configured Open Night Railway server when it starts. If the server answers the real game-protocol probe, it appears at the top of `AVAILABLE SERVERS`, is selected automatically, and can be joined with one click.

Configured public address:

```text
wss://open-night-production.up.railway.app
```

Do not add `:8080` or `:8765` to this public address.

## Updating the existing Railway service

1. Fully extract this ZIP.
2. Double-click `DEPLOY_OPEN_NIGHT_SERVER.bat`.
3. If Railway asks this new folder to link a project, choose the existing `open-night` project and `open-night` service. Do not create another project.
4. Wait for `Deployment successful` and the server startup status.

The deployment window deliberately remains open on success or failure. Railway is installed by npm as `railway.cmd`; the helper invokes it with `call` so control always returns to the visible deployment script.

The included `railway.toml` starts the server with Railway's assigned `$PORT`, Railway MySQL persistence, patch-reset mode, and LAN discovery disabled.

## One-time MySQL setup

1. In the existing `open-night` Railway project, click **+ New → Database → MySQL**.
2. Open the `open-night` game service, then open **Variables**.
3. Add these reference variables, replacing `MySQL` below only if the database service has a different name:

```text
MYSQLHOST=${{MySQL.MYSQLHOST}}
MYSQLPORT=${{MySQL.MYSQLPORT}}
MYSQLUSER=${{MySQL.MYSQLUSER}}
MYSQLPASSWORD=${{MySQL.MYSQLPASSWORD}}
MYSQLDATABASE=${{MySQL.MYSQLDATABASE}}
```

4. Deploy the staged Railway changes, then run `DEPLOY_OPEN_NIGHT_SERVER.bat`.

The server uses Railway's private service variables; do not paste database passwords into the repository.

## One-time human bug-review setup

1. Generate a private moderator token in PowerShell:

```powershell
[Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32))
```

2. In the Railway `open-night` service, add `PYMMO_BUG_ADMIN_TOKEN` with that
   generated value. Keep it secret and do not commit it to GitHub.
3. Deploy the staged change.
4. On your desktop, run `REVIEW_BUG_REPORTS.bat`. Paste the same token into its
   hidden prompt.

Player `/bug`, `/mapfeedback`, and F10 submissions are stored in MySQL as
`pending`. The review tool displays the report and opens its screenshot. It
requires you to type `APPROVE <report-id>` or `REJECT <report-id>` exactly.
Only approval exports a sanitized row/PNG into `feedback\approved\`, where it
can be committed and made available to ChatGPT. Player text never triggers code
changes automatically.

## Joining

1. Double-click `START_OPEN_NIGHT.bat`.
2. Select `DESKTOP CLIENT`.
3. Wait briefly for `INTERNET: ONLINE`.
4. The `Open Night Internet Server` row is already selected; click `JOIN`.

LAN discovery and Direct Connect remain available as fallbacks. Use made-up account-number identifiers during prototype testing because the phone-number field is not verified by SMS/OTP.

The Pygbag web client also reads the same public-server CSV and connects to this Railway address automatically. Each browser launch receives a synthetic prototype account identifier so multiple web players do not collide on one fixed login.

Run `DEPLOY_OPEN_NIGHT_SERVER.bat` from this version before testing it with friends so the existing `open-night` service serves the same map and database policy as every client.

v0.8.1 retains the `sms_messages` table for online and offline delivery. The strict version gate means friends must run `UPDATE_FRIEND_BUILD.bat` before reconnecting after the Railway service is upgraded.

## Prototype patch-reset policy

Accounts and inventory persist across ordinary Railway restarts. The server stores the active patch ID in MySQL. When `PYMMO_PATCH_ID` changes, it clears prototype accounts and inventories once, then records the new ID. Restarting or redeploying the same patch does not clear data again. The moderation queue is intentionally not cleared by a gameplay patch reset.

For every future patch, update `PYMMO_PATCH_ID` in `railway.toml`. Remove `PYMMO_RESET_DB_ON_PATCH=true` only when permanent persistence is ready.
