# Open Night v0.7.0 — Railway internet server

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

The included `railway.toml` starts the server with Railway's assigned `$PORT`, in-memory prototype accounts, and LAN discovery disabled.

## Joining

1. Double-click `START_OPEN_NIGHT.bat`.
2. Select `DESKTOP CLIENT`.
3. Wait briefly for `INTERNET: ONLINE`.
4. The `Open Night Internet Server` row is already selected; click `JOIN`.

LAN discovery and Direct Connect remain available as fallbacks. Use made-up account-number identifiers during prototype testing because the phone-number field is not verified by SMS/OTP.

The Pygbag web client also reads the same public-server CSV and connects to this Railway address automatically. Each browser launch receives a synthetic prototype account identifier so multiple web players do not collide on one fixed login.

v0.7.0 changes the authoritative map, bicycle safety rules and car–bicycle collision. Run `DEPLOY_OPEN_NIGHT_SERVER.bat` from this version before testing it with friends so the existing `open-night` service serves the same map as every client.

## Persistence limitation

Railway currently runs with `--memory-db`. Accounts, inventory, and position reset when Railway restarts or redeploys the service. Database persistence can be added after internet playtesting is stable.
