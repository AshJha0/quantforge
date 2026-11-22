# K-10: the version bump to 1.0.0

Prepared 2026-11-22 on branch `k-v1-rel` from `k-v1` 990ddd45. Not applied: the coordinator applies it on the final `k-v1` head, after every lane is merged and before PR #65 is marked ready.

Plain idea: a tag names one version, and the release job refuses a tag whose version is not in every build (`.github/workflows/release.yml`, job `release-changelog`, runs `tools/check_versions.py --expect "$version"`; read). One command makes the edits and checks them:

```bash
python tools/release/bump_version.py --self-test       # on a temporary copy; planted faults must fail
python tools/release/bump_version.py --to 1.0.0 --check  # prints the edits below, writes nothing
python tools/release/bump_version.py --to 1.0.0          # applies, then runs tools/check_versions.py --expect 1.0.0
```

## Machine edits (the script makes exactly these; read with `--check` on 990ddd45)

| File:line | Now | Edit |
|---|---|---|
| `python/pyproject.toml:7` | `version = "0.10.1"` | `version = "1.0.0"` |
| `python/quantforge_core/__init__.py:8` | `__version__ = "0.10.1"` (source-tree fallback) | `__version__ = "1.0.0"` |
| `python/uv.lock:368` | `quantforge-core` `version = "0.10.1"` | `version = "1.0.0"` |
| `rust/Cargo.toml:8` | `[workspace.package] version = "0.10.1"` | `version = "1.0.0"` (the CLI reports `env!("CARGO_PKG_VERSION")`, `rust/crates/quantforge-cli/src/main.rs:291`) |
| `rust/Cargo.lock:300, 308, 315` | `quantforge-bench`, `quantforge-cli`, `quantforge-core` `version = "0.10.1"` | `version = "1.0.0"` each; `rand_core 0.10.1` at line 346 is a third-party crate and is not touched |
| `java25/pom.xml:4` | `<version>0.10.1</version>` | `<version>1.0.0</version>` |
| `java25/src/main/java/org/quantforge/cli/Main.java:27` | `VERSION = "0.10.0"` | `VERSION = "1.0.0"` |
| `cpp26/CMakeLists.txt:2` | `project(quantforge_cpp26 VERSION 0.10.1 ...)` | `VERSION 1.0.0` (the CLI reports `QF_VERSION` = `PROJECT_VERSION`, line 115) |
| `tools/site_facts.json:10` | `"version": "0.10.1"` | `"version": "1.0.0"` |

## Finding: the Java CLI reports 0.10.0 today

`Main.java:27` says `0.10.0` while `pom.xml` says `0.10.1` (read 2026-11-22). The Java CLI's `version` command therefore reports `implementation_version` 0.10.0 on `main` and `k-v1`. `tools/check_versions.py` does not read `Main.java`, so the release gate would not have caught it; `bump_version.py` covers it. Proposed follow-up for the coordinator (not done here, because adding it now would turn repo-gates red until the bump): add `("java25/src/main/java/org/quantforge/cli/Main.java", r'String VERSION = "([^"]+)";', 1)` to `PLACES` in `tools/check_versions.py` in the same commit as the bump.

## Not touched: the CLI contract number 1.17.0

Held in `conformance/runner/runner.py:25`, `conformance/runner/stub_cli.py:68`, `cpp26/src/cli/dispatch.cpp:526`, `java25/src/main/java/org/quantforge/cli/Main.java:26`, `python/quantforge_core/cli/main.py:13`, and the docs. The script refuses 1.17.0 as a target and fails if any edited file's count of `1.17.0` would change (self-test checks it).

## Tests that assert the version

None outside `tools/check_versions.py --self-test`, which uses `1.0.0` and `0.10.1` as planted strings and needs no edit (`git grep -nE "0\.10\.[01]"` over tests, read 2026-11-22). The conformance runner records the CLI's `version` output but checks only `contract_version` (`conformance/runner/runner.py:248-253`).

## Prose edits (by hand, docs lane or coordinator; not in the script)

These are sentences, not version fields; each must change from "unreleased / bumped at v1.0.0" to "released":

- `tools/site_facts.json` keys `main_state` (line 5) and `next_stage` (line 13); then `python tools/status_glance.py --write` regenerates `README.md:32`.
- `README.md:100` ("the build version string on main reads 0.10.1 until the v1.0.0 bump").
- `CHANGELOG.md:3` heading `## Unreleased, for v1.0.0 ...` replaced by the text in `CHANGELOG_1.0.0.md` (the release job needs a `## 1.0.0` heading: `grep -Eq "^## 1\.0\.0([: ]|$)"`).
- `docs/releases/v0.10.1.md:5` keeps its wording (it is history), but its "reads 0.10.1" sentence becomes past tense.
- `docs/releases/v1.0.0.md`: fill every `{{generated}}` placeholder.

After the edits: `python tools/check_versions.py --expect 1.0.0`, `python tools/build_site.py` (fails on a stale README), `python research/test_preregs.py`, Rust `cargo build --locked` (the lock must match), Java `mvn -B -DskipTests package` (jar name `quantforge-1.0.0.jar`).
