# Trade Swing Bot DigitalOcean Deployment Runbook

## Purpose

This runbook documents how to deploy, validate, update, operate, and recover the Trade Swing Bot on the existing DigitalOcean AI CIO platform.

The Swing Bot remains a separate repository and runtime from the Trade Dividend Bot. Both may run on the same DigitalOcean Project and Droplet, but they must not share a virtual environment, state directory, results directory, scheduler, or systemd service.

All deployment and runtime behavior remains paper-only.

## Safety Rules

- `paper_trade_mode` must remain enabled.
- Live trading must remain disabled.
- Broker execution must remain disabled.
- No real orders may be placed.
- The server may pull from GitHub but should not push source changes.
- Do not place private keys, passwords, tokens, or `.env` contents in this document or in Git.
- Do not copy Swing Bot files into the Dividend Bot repository.
- Do not point Swing outputs at Dividend Bot state or results directories.

## Current Platform Layout

DigitalOcean Project:

```text
AI CIO Portfolio System
```

Initial Droplet:

```text
ai-cio-platform
```

Recommended filesystem layout:

```text
/home/tradebot/
├── Trade-Dividend-Bot/
│   ├── .venv/
│   ├── state/
│   ├── results/
│   ├── logs/
│   └── runtime/
├── Trade-Swing-Bot/
│   ├── .venv/
│   ├── state/
│   ├── results/
│   ├── logs/
│   └── runtime/
└── backups/
```

## GitHub Access

Repository:

```text
percyagenticmay27-commits/Trade-Swing-Bot
```

The DigitalOcean server uses a repository-scoped SSH deploy key for read-only access.

SSH alias:

```text
github-swing
```

Expected SSH configuration:

```sshconfig
Host github-swing
    HostName github.com
    User git
    IdentityFile /home/tradebot/.ssh/id_ed25519_swing
    IdentitiesOnly yes
```

Required permissions:

```bash
chmod 700 /home/tradebot/.ssh
chmod 600 /home/tradebot/.ssh/config
chmod 600 /home/tradebot/.ssh/id_ed25519_swing
chmod 644 /home/tradebot/.ssh/id_ed25519_swing.pub
chown -R tradebot:tradebot /home/tradebot/.ssh
```

Test access:

```bash
sudo -u tradebot ssh -T git@github-swing
```

A successful response identifies the Trade Swing Bot repository. The GitHub deploy key should have **Allow write access unchecked**.

## Initial Clone

```bash
cd /home/tradebot

sudo -u tradebot git clone \
  git@github-swing:percyagenticmay27-commits/Trade-Swing-Bot.git
```

Verify:

```bash
cd /home/tradebot/Trade-Swing-Bot

sudo -u tradebot git status
sudo -u tradebot git branch --show-current
sudo -u tradebot git log --oneline -5
sudo -u tradebot git remote -v
```

Expected branch:

```text
main
```

## Backup Before Deployment Changes

Before a major deployment or runtime change, protect the currently working platform.

```bash
cd /home/tradebot
mkdir -p backups

BACKUP_NAME="ai-cio-before-swing-change-$(date +%Y%m%d-%H%M%S)"

cp -a Trade-Dividend-Bot "backups/${BACKUP_NAME}-dividend"
tar -czf "backups/${BACKUP_NAME}-dividend.tar.gz" \
  "backups/${BACKUP_NAME}-dividend"

if [ -d Trade-Swing-Bot ]; then
  cp -a Trade-Swing-Bot "backups/${BACKUP_NAME}-swing"
  tar -czf "backups/${BACKUP_NAME}-swing.tar.gz" \
    "backups/${BACKUP_NAME}-swing"
fi

ls -lh backups/
```

The backup archive must remain outside both Git repositories.

## Virtual Environment

The Swing Bot uses its own virtual environment:

```text
/home/tradebot/Trade-Swing-Bot/.venv
```

Create it:

```bash
cd /home/tradebot/Trade-Swing-Bot

apt update
apt install -y python3-venv

sudo -u tradebot python3 -m venv .venv
sudo -u tradebot .venv/bin/python -m pip install --upgrade pip
```

Install repository dependencies only after reviewing the repository's current dependency file:

```bash
sudo -u tradebot .venv/bin/python -m pip install -r requirements.txt
```

Do not use the Dividend Bot virtual environment for Swing Bot commands.

## Runtime Directories

```bash
cd /home/tradebot/Trade-Swing-Bot

sudo -u tradebot mkdir -p state results logs runtime
chown -R tradebot:tradebot /home/tradebot/Trade-Swing-Bot
```

Expected ownership:

```text
tradebot:tradebot
```

## Environment Configuration

The deployment environment file should be stored outside version control or excluded by `.gitignore`.

Recommended path:

```text
/home/tradebot/Trade-Swing-Bot/.env
```

Minimum safety intent:

```bash
PAPER_TRADE_MODE=true
LIVE_TRADING_ENABLED=false
BROKER_EXECUTION_ENABLED=false
```

Use only environment variable names already defined by the Swing repository. Do not invent replacements for existing configuration contracts.

Protect the file:

```bash
chown tradebot:tradebot /home/tradebot/Trade-Swing-Bot/.env
chmod 600 /home/tradebot/Trade-Swing-Bot/.env
```

Never print secret values into logs or screenshots.

## Pre-Deployment Validation

Read the repository instructions before operating the deployment:

```text
docs/README_FOR_AI_DEVELOPERS.md
docs/STAGE_9_ENTERPRISE_INTEGRATION_HANDOFF.md
```

Compile the source tree:

```bash
cd /home/tradebot/Trade-Swing-Bot
sudo -u tradebot .venv/bin/python -m compileall src
```

Run the repository test suite:

```bash
sudo -u tradebot .venv/bin/python -m pytest -v
```

At minimum, confirm tests covering these areas pass:

- paper-only safety constants;
- strategy calculations and frozen schemas;
- Swing Trader Enterprise plugin;
- Enterprise contracts;
- health and status output;
- AI CIO discovery;
- no broker execution;
- no live-order placement.

Do not enable a timer or persistent service until the manual validation passes.

## Manual Paper Cycle

Use the official repository launcher or entry point documented by the Swing repository. Do not guess or create a replacement launcher during deployment.

General execution form:

```bash
cd /home/tradebot/Trade-Swing-Bot
sudo -u tradebot .venv/bin/python <official-entry-point>
```

A successful manual run must confirm:

```text
PAPER ONLY
No live orders
No broker execution
Enterprise plugin initialized
Enterprise contracts written
Expected reports generated
```

Inspect generated files only under the Swing Bot directories:

```bash
find state results logs runtime -maxdepth 3 -type f -printf '%TY-%Tm-%Td %TH:%TM:%TS %p\n' \
  | sort -r \
  | head -100
```

## Enterprise AI CIO Integration

The Swing Bot must publish its own Enterprise strategy contract. The target logical identity is:

```text
strategy_id: swing
plugin_type: STRATEGY
strategy_plugin: true
paper_trade_mode: true
live_trading_enabled: false
broker_execution_enabled: false
capital_movement_enabled: false
```

The AI CIO should discover Swing and Dividend as separate strategies while the repositories remain independent.

Expected investor portal result after integration:

```text
Eligible Strategies: 2

Dividend Income Strategy
Swing Trader Strategy
```

Do not manually copy a temporary strategy record into the Dividend repository. Use the frozen Enterprise registry and discovery contracts.

## systemd Naming Standard

Use Swing-specific unit names. Do not reuse Dividend unit names.

Recommended names:

```text
swing-bot.service
swing-bot.timer
swing-enterprise-runtime.service
```

The final service command must use the repository's official launcher.

Example structure only:

```ini
[Unit]
Description=Trade Swing Bot Paper Cycle
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=tradebot
Group=tradebot
WorkingDirectory=/home/tradebot/Trade-Swing-Bot
EnvironmentFile=/home/tradebot/Trade-Swing-Bot/.env
ExecStart=/home/tradebot/Trade-Swing-Bot/.venv/bin/python <official-entry-point>
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=false

[Install]
WantedBy=multi-user.target
```

Do not install this example verbatim until `<official-entry-point>` is replaced with the validated repository entry point.

After creating or changing a unit:

```bash
systemctl daemon-reload
systemctl start swing-bot.service
systemctl status swing-bot.service --no-pager -l
journalctl -u swing-bot.service -n 100 --no-pager
```

A successful oneshot service may end as:

```text
Active: inactive (dead)
status=0/SUCCESS
```

Only enable the timer after a successful manual service run:

```bash
systemctl enable --now swing-bot.timer
systemctl status swing-bot.timer --no-pager -l
systemctl list-timers --all | grep -i swing
```

## Standard GitHub Update Procedure

Before pulling, inspect the deployment state:

```bash
cd /home/tradebot/Trade-Swing-Bot

sudo -u tradebot git status
sudo -u tradebot git branch --show-current
sudo -u tradebot git fetch origin
sudo -u tradebot git rev-list --left-right --count HEAD...origin/main
```

If the working tree is clean and the branch can be fast-forwarded:

```bash
sudo -u tradebot git switch main
sudo -u tradebot git pull --ff-only origin main
```

Verify:

```bash
sudo -u tradebot git rev-list --left-right --count HEAD...origin/main
sudo -u tradebot git log --oneline -5
```

Expected comparison after update:

```text
0    0
```

Do not use `git reset --hard`, `git clean -fd`, or `git stash pop` without first reviewing deployment-generated files and preserving persistent state.

## Dependency Update Procedure

After a pull, first check whether dependency files changed:

```bash
sudo -u tradebot git diff HEAD@{1}..HEAD -- requirements.txt pyproject.toml setup.py setup.cfg
```

If no dependency file changed, do not reinstall packages solely because application code changed.

If a dependency file changed:

```bash
sudo -u tradebot .venv/bin/python -m pip install -r requirements.txt
```

Then rerun compile and focused deployment tests.

## Logs and Diagnostics

Repository logs:

```text
/home/tradebot/Trade-Swing-Bot/logs
```

systemd logs:

```bash
journalctl -u swing-bot.service -n 100 --no-pager
journalctl -u swing-bot.timer -n 100 --no-pager
```

Follow live service output:

```bash
journalctl -u swing-bot.service -f
```

Inspect recent repository outputs:

```bash
cd /home/tradebot/Trade-Swing-Bot
find results logs state runtime -maxdepth 3 -type f \
  -printf '%TY-%Tm-%Td %TH:%TM:%TS %s %p\n' \
  | sort -r \
  | head -100
```

## Ownership Repair

If files were accidentally created as root:

```bash
chown -R tradebot:tradebot /home/tradebot/Trade-Swing-Bot
```

Then verify:

```bash
find /home/tradebot/Trade-Swing-Bot \! -user tradebot -o \! -group tradebot
```

Review results before changing ownership outside the repository.

## Rollback Procedure

Stop Swing services before rollback:

```bash
systemctl stop swing-bot.timer 2>/dev/null || true
systemctl stop swing-bot.service 2>/dev/null || true
```

Preserve the failed deployment:

```bash
cd /home/tradebot
mv Trade-Swing-Bot "Trade-Swing-Bot-failed-$(date +%Y%m%d-%H%M%S)"
```

Restore the selected backup:

```bash
cd /home/tradebot
cp -a backups/<swing-backup-directory> Trade-Swing-Bot
chown -R tradebot:tradebot Trade-Swing-Bot
```

Validate before restarting:

```bash
cd /home/tradebot/Trade-Swing-Bot
sudo -u tradebot git status
sudo -u tradebot .venv/bin/python -m compileall src
sudo -u tradebot .venv/bin/python -m pytest -v
```

Restart only after validation succeeds.

## Disaster Recovery Checklist

Record these items securely outside Git:

- DigitalOcean Project name;
- Droplet name and region;
- server public IP;
- `tradebot` Linux user;
- repository names and default branches;
- SSH deploy-key titles;
- DNS names and Nginx routes;
- systemd service and timer names;
- `.env` backup location;
- backup archive location;
- official Swing launcher;
- runtime schedule;
- expected registry and health output paths.

Do not record private key contents, passwords, app passwords, or tokens in documentation.

## Deployment Completion Checklist

- [ ] Swing repository cloned with the read-only Swing deploy key.
- [ ] `main` matches `origin/main`.
- [ ] Separate `.venv` created.
- [ ] Dependencies installed from the Swing repository.
- [ ] `state`, `results`, `logs`, and `runtime` exist.
- [ ] Ownership is `tradebot:tradebot`.
- [ ] Environment file is protected with mode `600`.
- [ ] Source compilation passes.
- [ ] Full or approved deployment tests pass.
- [ ] Manual paper cycle succeeds.
- [ ] No live-order or broker-execution behavior is present.
- [ ] Enterprise Swing strategy contract is generated.
- [ ] AI CIO discovery sees the Swing strategy.
- [ ] systemd service succeeds manually.
- [ ] Timer is enabled only after service validation.
- [ ] Logs and outputs are reviewed.
- [ ] Backup and rollback paths are verified.

## Operational Boundary

The Dividend Bot and Swing Bot may share the AI CIO platform and investor portal, but they remain separate strategy systems. Integration occurs through Enterprise contracts, registry discovery, health/status reporting, and governed paper-capital allocation—not through shared source trees or direct imports between repositories.
