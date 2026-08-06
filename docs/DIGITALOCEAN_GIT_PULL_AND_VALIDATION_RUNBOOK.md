# DigitalOcean Git Pull and Validation Runbook

## Purpose

This document is the permanent operational reference for updating and validating the Trade Swing Bot on the DigitalOcean server.

Use this runbook to avoid repeating repository-location, Linux-user, SSH-key, Git-pull, installation, compilation, and test-path investigations.

## Authoritative Repository Information

- GitHub repository: `percyagenticmay27-commits/Trade-Swing-Bot`
- DigitalOcean repository root: `/home/tradebot/Trade-Swing-Bot`
- Swing application directory: `/home/tradebot/Trade-Swing-Bot/main`
- Required Linux user for Git operations: `tradebot`
- Repository-specific SSH key: `/home/tradebot/.ssh/id_ed25519_swing`
- Python virtual environment: `/home/tradebot/Trade-Swing-Bot/main/.venv`

## Permanent Directory Rule

There are two different working directories with two different purposes.

### Repository root — Git operations only

Run `git fetch`, `git pull`, `git status`, `git log`, branch inspection, and remote inspection from:

```text
/home/tradebot/Trade-Swing-Bot
```

### Application directory — Python operations only

Run editable installation, `py_compile`, `pytest`, publishers, runtime scripts, and email scripts from:

```text
/home/tradebot/Trade-Swing-Bot/main
```

Do not troubleshoot Git from `Trade-Swing-Bot/main`. Although Git can sometimes discover the parent repository, the repository root is the authoritative Git working directory.

## Permanent Linux User Rule

GitHub access for this repository must use the `tradebot` Linux account.

Do not run repository Git operations as `root`.

Start a login shell as `tradebot`:

```bash
sudo -iu tradebot
```

Confirm the active identity:

```bash
whoami
pwd
```

Expected:

```text
tradebot
/home/tradebot
```

## Permanent SSH Identity Rule

The Swing repository uses this SSH key:

```text
/home/tradebot/.ssh/id_ed25519_swing
```

The generic key may authenticate to GitHub but may not have access to the private Swing repository. A successful generic `ssh -T` response does not prove repository access.

Bind the repository permanently to the Swing-specific key from the repository root:

```bash
cd /home/tradebot/Trade-Swing-Bot

git config core.sshCommand \
  "ssh -i /home/tradebot/.ssh/id_ed25519_swing -o IdentitiesOnly=yes"
```

Verify the saved setting:

```bash
git config --get core.sshCommand
```

Expected:

```text
ssh -i /home/tradebot/.ssh/id_ed25519_swing -o IdentitiesOnly=yes
```

Verify real repository access, not only GitHub authentication:

```bash
git ls-remote origin | head
```

Success means commit hashes and refs are returned. Do not proceed to `git pull` when this command returns `Repository not found`, `Permission denied`, or a hostname-resolution error.

## Standard Git Pull Procedure

### 1. Log in as `tradebot`

```bash
sudo -iu tradebot
```

### 2. Enter the repository root

```bash
cd /home/tradebot/Trade-Swing-Bot
```

### 3. Confirm repository identity and branch

```bash
pwd
git rev-parse --show-toplevel
git remote -v
git branch --show-current
git status --short
```

Expected repository root:

```text
/home/tradebot/Trade-Swing-Bot
```

Expected remote repository:

```text
git@github.com:percyagenticmay27-commits/Trade-Swing-Bot.git
```

### 4. Confirm SSH binding and repository access

```bash
git config --get core.sshCommand
git ls-remote origin | head
```

### 5. Fetch and pull the required branch

Replace `<BRANCH>` with the branch being deployed.

```bash
git fetch origin

git pull --ff-only origin <BRANCH>
```

Current Phase 2 branch example:

```bash
git fetch origin

git pull --ff-only origin \
  feature/swing-phase2-enterprise-market-data
```

### 6. Confirm the pull

```bash
git log -8 --oneline --decorate
git status --short
```

A successful fast-forward pull normally includes output similar to:

```text
Updating <old-sha>..<new-sha>
Fast-forward
```

## Standard Python Installation Procedure

After the Git pull succeeds, move to the application directory:

```bash
cd /home/tradebot/Trade-Swing-Bot/main
source .venv/bin/activate
python -m pip install -e .
```

Confirm the interpreter and working directory:

```bash
pwd
which python
python --version
```

Expected directory:

```text
/home/tradebot/Trade-Swing-Bot/main
```

Expected interpreter prefix:

```text
/home/tradebot/Trade-Swing-Bot/main/.venv/
```

## Standard Compilation Procedure

Compile only the files involved in the change. Example for Enterprise strategy allocation and KPI publication:

```bash
cd /home/tradebot/Trade-Swing-Bot/main
source .venv/bin/activate

python -m py_compile \
  src/swing_trade_bot/enterprise_strategy_allocation_discovery.py \
  src/swing_trade_bot/enterprise_strategy_kpi_publisher.py \
  src/swing_trade_bot/enterprise_strategy_kpi_publisher_v21.py \
  publish_enterprise_strategy_kpis_v21.py \
  run_swing_bot_cycle.py \
  src/swing_trade_bot/daily_swing_email.py
```

`py_compile` passes when the command returns to the prompt without a traceback or error message.

## Standard Focused Test Procedure

Example for Enterprise allocation discovery, KPI publication, and Swing email behavior:

```bash
cd /home/tradebot/Trade-Swing-Bot/main
source .venv/bin/activate

python -m pytest \
  tests/test_enterprise_strategy_allocation_discovery.py \
  tests/test_enterprise_strategy_kpi_publisher.py \
  tests/test_enterprise_strategy_kpi_publisher_v21.py \
  tests/test_daily_swing_email.py \
  -v
```

Do not run production publishers, runtime cycles, or forced email sends until compilation and the required focused tests pass.

## One-Block Deployment Command Template

Use this template after replacing `<BRANCH>` and the compile/test file lists for the current change:

```bash
sudo -iu tradebot

cd /home/tradebot/Trade-Swing-Bot

git config core.sshCommand \
  "ssh -i /home/tradebot/.ssh/id_ed25519_swing -o IdentitiesOnly=yes"

git ls-remote origin | head
git fetch origin
git pull --ff-only origin <BRANCH>
git log -8 --oneline --decorate

cd /home/tradebot/Trade-Swing-Bot/main
source .venv/bin/activate
python -m pip install -e .

python -m py_compile <CHANGED_PYTHON_FILES>
python -m pytest <FOCUSED_TEST_FILES> -v
```

## Error Interpretation

### `Could not resolve hostname github.com`

This is a server DNS or network problem.

Check:

```bash
getent hosts github.com
curl -I https://github.com
```

### `Could not resolve hostname github-swing` or another alias

Git or SSH is using an undefined hostname alias. Inspect:

```bash
git remote -v
git config --get remote.origin.url
```

The normal remote should use `github.com` unless a valid SSH configuration explicitly defines another alias.

### `Permission denied (publickey)`

The active Linux user or SSH key is wrong. Confirm:

```bash
whoami
git config --get core.sshCommand
```

For this repository, use:

```text
tradebot
/home/tradebot/.ssh/id_ed25519_swing
```

### `Repository not found` after successful `ssh -T`

GitHub recognized a key, but that key does not have access to this private repository. Test the Swing-specific key directly:

```bash
GIT_SSH_COMMAND="ssh -i /home/tradebot/.ssh/id_ed25519_swing -o IdentitiesOnly=yes" \
  git ls-remote \
  git@github.com:percyagenticmay27-commits/Trade-Swing-Bot.git
```

If refs are returned, save the repository-level `core.sshCommand` binding described above.

### `file or directory not found` during pytest

First confirm the pull succeeded and the file exists on disk:

```bash
cd /home/tradebot/Trade-Swing-Bot

git log -8 --oneline
find main -path '*<EXPECTED_FILENAME>*' -print
```

Do not treat a missing test file as a production-code failure when the branch changes were not successfully pulled.

### Deleted tracked `__pycache__` files in `git status`

Do not commit generated Python cache files. They are unrelated to production logic. Do not use them as evidence that the pull failed.

### Untracked runtime files under `main/results`

Runtime results may be untracked and must not be committed unless the project specifically requires a fixture or documented artifact. Preserve runtime evidence, but keep it separate from source-control changes.

## Permanent Safety Rules

- Run Git as `tradebot`, not `root`.
- Run Git from `/home/tradebot/Trade-Swing-Bot`.
- Run Python from `/home/tradebot/Trade-Swing-Bot/main`.
- Use `/home/tradebot/.ssh/id_ed25519_swing` for this repository.
- Confirm access with `git ls-remote origin` before diagnosing branch or file problems.
- Use `git pull --ff-only` to prevent unintended merge commits on the server.
- Do not commit `__pycache__`, virtual-environment files, or ordinary runtime results.
- Do not run production validation until installation, compilation, and focused tests pass.
- Preserve paper-only behavior and never add broker execution while performing deployment maintenance.

## Quick Reference

```text
Repository:       percyagenticmay27-commits/Trade-Swing-Bot
Git directory:    /home/tradebot/Trade-Swing-Bot
Python directory: /home/tradebot/Trade-Swing-Bot/main
Linux user:       tradebot
SSH key:          /home/tradebot/.ssh/id_ed25519_swing
Virtual env:      /home/tradebot/Trade-Swing-Bot/main/.venv
Pull policy:      git pull --ff-only origin <BRANCH>
```
