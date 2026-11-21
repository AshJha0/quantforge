# Security policy

QuantForge is a one-person, zero-spend project with no service, no hosted deployment and no user accounts: it is a library and command-line tool you build and run yourself. This page says honestly what that means for security reports.

## Supported versions

Only the latest release and the `main` branch receive fixes. Older tags are kept as history and are not patched; upgrade to the latest release instead. The latest release is named on the [releases page](https://github.com/AshJha0/quantforge/releases) and in the README status block.

| Version | Fixes |
|---|---|
| Latest release | yes |
| `main` (unreleased) | yes |
| Any older tag | no |

## How to report

Report a vulnerability privately with "Report a vulnerability" on the repository's Security tab (GitHub private vulnerability reporting, enabled on this repository; read through the GitHub API on 2026-11-20). Do not open a public issue for a vulnerability. Include the version or commit, the language build (Java, C++, Python or Rust), the command or input that shows the problem, and what you expected.

## What to expect

- One maintainer reads reports. The aim is a first reply within a week; there is no service-level agreement and it can take longer.
- If the report is confirmed, the fix lands on `main` with a test or golden case that fails without it, and is named in `CHANGELOG.md` and the next release notes. You are credited unless you ask not to be.
- If the report is declined, the reply says why.
- No bug bounty is offered: the project has no budget.

## Scope

In scope: crashes, hangs, memory-safety faults or undefined behaviour reachable from CLI input (the fuzz harness in `conformance/fuzz/` looks for these; see the known issues for its current state), and anything in the GitHub Actions workflows that could leak a token or write where it should not.

Out of scope: wrong numbers that are not a security matter (open a normal issue), and the third-party libraries themselves (report those upstream).

## For contributors

Do not commit credentials, private keys, account identifiers, proprietary market data or confidential client information. Treat all external market data and instrument metadata as untrusted input and validate schemas, ranges, timestamps and units.
