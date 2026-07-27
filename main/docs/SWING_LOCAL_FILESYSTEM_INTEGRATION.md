# Swing Local Filesystem Integration

## Purpose

Allow the AI CIO and Trade Swing Bot to run on the same DigitalOcean server while remaining independent systems. Milestone 1 uses read-only local artifact discovery. No API, network service, database connection, Agentic transport, direct Python imports, or broker execution is required.

## Server Layout

```text
/home/tradebot/
├── Trade-Dividend-Bot/
├── Trade-Swing-Bot/
└── AI-CIO/
```

The Swing plugin root is `/home/tradebot/Trade-Swing-Bot/main` and its CIO artifacts are under `/home/tradebot/Trade-Swing-Bot/main/results`.

## Registration Artifact

The Swing Bot generates:

```text
results/swing_local_filesystem_registration.json
```

The AI CIO reads this registration and then reads the referenced final JSON artifacts only.

## CIO Consumer Rules

The AI CIO must:

- validate `plugin_id == SWING-001`
- validate `transport == LOCAL_FILESYSTEM`
- read the plugin manifest, output contract, schema registry, strategy registration, capability profiles, committee governance, and CIO acceptance report
- require the acceptance report to state `READY_FOR_CIO`
- read only reports allowed by the output contract
- use file modification times for freshness
- ignore `.tmp` files
- remain read-only
- never import or execute Swing Bot Python modules

## Atomic Publishing

Every shared JSON artifact must use this pattern:

```text
write artifact.json.tmp
validate artifact.json.tmp
fsync artifact.json.tmp
rename artifact.json.tmp -> artifact.json
```

The rename occurs through `os.replace`, which prevents the CIO from reading a partially written final file.

## Freshness

Default states:

- `FRESH`: less than 1,440 minutes old
- `WARNING`: 1,440 to less than 2,880 minutes old
- `STALE`: 2,880 minutes old or older
- `MISSING`: absent or temporary file

These thresholds are configurable without changing the integration transport.

## Permissions

Both repositories should run under the non-root `tradebot` account:

```bash
sudo chown -R tradebot:tradebot /home/tradebot/Trade-Swing-Bot
sudo chmod -R u+rwX,go-rwx /home/tradebot/Trade-Swing-Bot
```

Because the AI CIO also runs as `tradebot`, it can read final Swing artifacts without exposing them to other server users.

## Safety Boundary

Permanent Milestone 1 rules:

- paper-only
- advisory-only
- local filesystem transport only
- read-only CIO consumer
- no automatic activation
- no real capital movement
- no broker or Robinhood execution
- no direct database writes
- no imports of Swing Bot runtime modules by AI CIO
