# Trade Swing Bot DigitalOcean Deployment Supplement

## Purpose

This document contains only the deployment details that are specific to the Trade Swing Bot.

The authoritative shared standard is:

```text
Trade-Dividend-Bot/docs/ENTERPRISE_DIGITALOCEAN_DEPLOYMENT_STANDARD_V1.md
```

The shared standard controls repository isolation, deploy keys, backups, virtual environments, dependency handling, validation, systemd, updates, logs, recovery, and Enterprise AI CIO integration.

If this supplement conflicts with the shared standard, the shared standard wins.

## Repository Identity

```text
Repository: percyagenticmay27-commits/Trade-Swing-Bot
Server path: /home/tradebot/Trade-Swing-Bot
Production branch: main
Runtime user: tradebot
Runtime group: tradebot
```

## GitHub Deploy Key

The Swing Bot uses a repository-scoped, read-only deploy key.

```text
SSH alias: github-swing
Private key: /home/tradebot/.ssh/id_ed25519_swing
Public key: /home/tradebot/.ssh/id_ed25519_swing.pub
Allow write access: unchecked
```

Expected SSH configuration:

```sshconfig
Host github-swing
    HostName github.com
    User git
    IdentityFile /home/tradebot/.ssh/id_ed25519_swing
    IdentitiesOnly yes
```

Test:

```bash
sudo -u tradebot ssh -T git@github-swing
```

Clone:

```bash
cd /home/tradebot
sudo -u tradebot git clone \
  git@github-swing:percyagenticmay27-commits/Trade-Swing-Bot.git
```

## Filesystem and Runtime Isolation

```text
/home/tradebot/Trade-Swing-Bot/.venv
/home/tradebot/Trade-Swing-Bot/state
/home/tradebot/Trade-Swing-Bot/results
/home/tradebot/Trade-Swing-Bot/logs
/home/tradebot/Trade-Swing-Bot/runtime
/home/tradebot/Trade-Swing-Bot/.env
```

The Swing Bot must not use the Dividend Bot virtual environment, state, results, logs, runtime directories, launcher, timer, or systemd unit.

## Required Documentation

Before deployment or maintenance, read:

```text
docs/README_FOR_AI_DEVELOPERS.md
docs/STAGE_9_ENTERPRISE_INTEGRATION_HANDOFF.md
```

Also read the shared Enterprise deployment standard from the Enterprise Core repository.

## Virtual Environment

```bash
cd /home/tradebot/Trade-Swing-Bot
sudo -u tradebot python3 -m venv .venv
sudo -u tradebot .venv/bin/python -m pip install --upgrade pip
sudo -u tradebot .venv/bin/python -m pip install -r requirements.txt
```

## Runtime Directories

```bash
cd /home/tradebot/Trade-Swing-Bot
sudo -u tradebot mkdir -p state results logs runtime
chown -R tradebot:tradebot /home/tradebot/Trade-Swing-Bot
```

## Environment Safety

The exact variable names must come from the Swing repository's existing configuration contract.

The deployed configuration must preserve:

```text
paper_trade_mode=true
live_trading_enabled=false
broker_execution_enabled=false
capital_movement_enabled=false
```

Protect the environment file:

```bash
chown tradebot:tradebot /home/tradebot/Trade-Swing-Bot/.env
chmod 600 /home/tradebot/Trade-Swing-Bot/.env
```

## Validation

```bash
cd /home/tradebot/Trade-Swing-Bot
sudo -u tradebot .venv/bin/python -m compileall src
sudo -u tradebot .venv/bin/python -m pytest -v
```

At minimum, confirm coverage for:

- paper-only safety;
- frozen strategy calculations and schemas;
- `SwingTraderEnterprisePlugin`;
- Enterprise contracts;
- strategy registry publishing;
- health and status outputs;
- AI CIO discovery;
- no broker execution;
- no live-order placement.

## Manual Paper Cycle

Use only the official entry point already defined by the repository. Do not invent a deployment launcher.

General form:

```bash
cd /home/tradebot/Trade-Swing-Bot
sudo -u tradebot .venv/bin/python <official-entry-point>
```

A valid run must confirm:

```text
PAPER ONLY
No live orders
No broker execution
Enterprise plugin initialized
Enterprise contracts written
Expected Swing outputs generated
```

## Enterprise Strategy Identity

The Swing Bot must publish an eligible strategy plugin logically equivalent to:

```text
strategy_id: swing
plugin_type: STRATEGY
strategy_plugin: true
status: READY
enabled: true
health: HEALTHY
paper_trade_mode: true
live_trading_enabled: false
broker_execution_enabled: false
capital_movement_enabled: false
```

After consolidated AI CIO discovery, the investor allocation portal should be able to display both:

```text
Dividend Income Strategy
Swing Trader Strategy
```

Do not manually copy temporary Swing records into the Dividend repository.

## systemd Names

Use Swing-specific units only:

```text
swing-bot.service
swing-bot.timer
swing-enterprise-runtime.service
```

The final `ExecStart` must use the validated official Swing entry point.

Required service paths:

```text
WorkingDirectory=/home/tradebot/Trade-Swing-Bot
EnvironmentFile=/home/tradebot/Trade-Swing-Bot/.env
ExecStart=/home/tradebot/Trade-Swing-Bot/.venv/bin/python <official-entry-point>
User=tradebot
Group=tradebot
```

Enable the Swing timer only after a successful manual paper cycle and successful systemd oneshot run.

## Update Commands

```bash
cd /home/tradebot/Trade-Swing-Bot
sudo -u tradebot git fetch origin
sudo -u tradebot git switch main
sudo -u tradebot git pull --ff-only origin main
sudo -u tradebot git rev-list --left-right --count HEAD...origin/main
```

Expected:

```text
0    0
```

Check dependency changes before reinstalling:

```bash
sudo -u tradebot git diff HEAD@{1}..HEAD -- \
  requirements.txt pyproject.toml setup.py setup.cfg
```

## Logs

```bash
journalctl -u swing-bot.service -n 100 --no-pager
journalctl -u swing-bot.timer -n 100 --no-pager
```

Repository outputs remain under:

```text
/home/tradebot/Trade-Swing-Bot/results
/home/tradebot/Trade-Swing-Bot/logs
/home/tradebot/Trade-Swing-Bot/state
/home/tradebot/Trade-Swing-Bot/runtime
```

## Completion Checklist

- repository cloned with the Swing read-only deploy key;
- branch is `main` and matches `origin/main`;
- separate `.venv` created;
- dependencies installed from Swing dependency files;
- compile and tests pass;
- paper-only flags remain locked;
- manual paper cycle passes;
- Enterprise strategy contract is published;
- AI CIO can discover the Swing strategy;
- Swing-specific systemd service passes;
- timer enabled only after validation;
- Dividend Bot remains operational and isolated.
