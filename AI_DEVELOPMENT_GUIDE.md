# AI Development Guide

## Purpose
This document is the primary guide for AI-assisted development of Trade-Swing-Bot.

## Core Principles
- Paper trading only.
- No real order execution.
- No Robinhood execution or brokerage API integration.
- paper_trade_mode=True is mandatory.

## Architecture
- Modular Python modules.
- Single responsibility per module.
- Prefer dependency injection where appropriate.
- Read existing outputs before creating new ones.

## Testing Standards
- Every production module should have corresponding unit tests.
- Validate JSON, CSV, and Markdown outputs.
- Do not modify production code solely to satisfy tests.

## Versioning
- Freeze completed modules with documentation.
- Preserve backward compatibility unless intentionally changing a major version.

## Reporting
- Outputs should be JSON, CSV, and Markdown where applicable.
- Missing optional inputs should generate warnings rather than failures.

## Safety Requirements
- Never generate buy, sell, or order execution code.
- Never generate live brokerage integrations.
- Preserve paper-only behavior throughout the codebase.
