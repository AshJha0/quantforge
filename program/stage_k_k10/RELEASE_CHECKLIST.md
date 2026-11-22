# K-10: v1.0.0 release checklist

Prepared 2026-11-22 on branch `k-v1-rel` (from `k-v1` 990ddd45). Source for every step: `.github/workflows/release.yml` (read), `tools/release_verify.py` (read), `.github/workflows/docs.yml` (read), ruleset 26732064 (read with `gh api`, GET only). Order follows `STAGE_K_RESUME.md` session 5 "FIRST THING NEXT" item 6. Never `gh pr merge --auto`.

## 0. Before PR #65 is marked ready

1. Every lane merged into `k-v1`; four-build verification at the head (lane rules).
2. Version bump on `k-v1` (see `VERSION_BUMP.md`):
   ```bash
   python tools/release/bump_version.py --self-test
   python tools/release/bump_version.py --to 1.0.0
   ```
   plus the prose edits, the CHANGELOG heading from `CHANGELOG_1.0.0.md`, and every `{{generated}}` in `docs/releases/v1.0.0.md` filled. Then `python tools/outside_shares.py --check`, `python tools/case_figures.py --check`, `python tools/build_site.py`, `python research/test_preregs.py`, the banned-word `git grep` named in the lane rules (must print nothing).
3. **KR-225: strict required status checks ON** (owner decision: just before PR #65 is ready). Read 2026-11-22 (GET): ruleset `main`, enforcement `active`, target `branch`, conditions `~DEFAULT_BRANCH`, bypass actors none, 15 required checks, `strict_required_status_checks_policy: false`. The update endpoint is `PUT /repos/{owner}/{repo}/rulesets/{id}` and replaces the whole `rules` array, so send the current ruleset with only that one field changed (no `jq` on this machine; Python does the edit):
   ```bash
   gh api repos/AshJha0/quantforge/rulesets/26732064 > rs_before.json
   python -c "import json; d=json.load(open('rs_before.json')); [r['parameters'].__setitem__('strict_required_status_checks_policy', True) for r in d['rules'] if r['type']=='required_status_checks']; json.dump({k: d[k] for k in ('name','target','enforcement','conditions','bypass_actors','rules')}, open('rs_after.json','w'), indent=1)"
   gh api -X PUT repos/AshJha0/quantforge/rulesets/26732064 --input rs_after.json --jq '.rules[] | select(.type=="required_status_checks") | .parameters.strict_required_status_checks_policy'
   ```
   The last command must print `true`. Check the 15 contexts are unchanged: `gh api repos/AshJha0/quantforge/rulesets/26732064 --jq '[.rules[]|select(.type=="required_status_checks").parameters.required_status_checks[].context]|length'` prints `15`. Rollback: `gh api -X PUT repos/AshJha0/quantforge/rulesets/26732064 --input rs_before_trimmed.json` (same trim of `rs_before.json`). Not run by this lane (read-only instruction); whether the token may PUT is not tested (the GET says `current_user_can_bypass: never`, which concerns bypass, not edit rights; inferred).
   With strict on, PR #65 must be up to date with `main` before it can merge; `main` = 11ba1b40 has not moved, so no update is expected (read 2026-11-22).

## 1. Merge PR #65

```bash
gh pr ready 65 --repo AshJha0/quantforge
gh pr checks 65 --repo AshJha0/quantforge --watch
gh pr merge 65 --repo AshJha0/quantforge --merge        # never --auto
git fetch origin && git rev-parse origin/main            # record the merge commit M
gh run list --repo AshJha0/quantforge --branch main --limit 30   # wait: every workflow on M green (Docs deploys the site)
python tools/check_versions.py --expect 1.0.0             # on a checkout of M
```

## 2. Tag and release run

The workflow triggers on a tag `v[0-9]+.[0-9]+.[0-9]+`; it reruns the four language CIs, refuses a tag without a `## 1.0.0` CHANGELOG heading or with any build not at 1.0.0, builds, attests and creates the release with `GITHUB_TOKEN`.

```bash
git tag -a v1.0.0 M -m "QuantForge v1.0.0: stage K closed"   # M = the merge commit on main
git push origin v1.0.0
gh run list --repo AshJha0/quantforge --workflow release.yml --limit 1
gh run watch <run-id> --repo AshJha0/quantforge --exit-status
gh release view v1.0.0 --repo AshJha0/quantforge
```

Jobs that must all pass: `release-changelog`, `release-python-ci`, `release-rust-ci`, `release-java-ci`, `release-cpp-ci`, `release-build-{python,rust,java,cpp}`, `release`, `release-verify` (KR-223 check RE2; first run ever, never run before a tag). If `release-changelog` fails, nothing was published: fix on `main` by PR, delete and re-push the tag only if no release exists (`gh release view v1.0.0` errors).

## 3. `gh attestation verify` on each asset

Expected assets (names from the workflow and the v0.10.0 record `benchmarks/results/k7/v0.10.0-attestations-2026-11-20.json`): `quantforge_core-1.0.0-py3-none-any.whl`, `quantforge_core-1.0.0.tar.gz`, `quantforge-rust-cli-1.0.0-linux-x86_64.tar.gz`, `quantforge-cli.jar` (Java; check the name on the release: v0.10.0 shipped `quantforge-cli.jar`), `quantforge-cli-1.0.0-linux-x86_64.tar.gz` (C++), `quantforge-1.0.0.cdx.json`, `SHA256SUMS`.

```bash
mkdir -p rel-1.0.0 && gh release download v1.0.0 --repo AshJha0/quantforge --dir rel-1.0.0
cd rel-1.0.0 && sha256sum -c SHA256SUMS
for f in *; do echo "== $f"; gh attestation verify "$f" --repo AshJha0/quantforge || echo "FAILED $f"; done
cd .. && python tools/release_verify.py --dir rel-1.0.0 --repo AshJha0/quantforge --out benchmarks/results/k7/v1.0.0-attestations-<date>.json
```

Every asset must say verified; `release_verify.py` also checks the SBOM's presence and that a one-byte-changed copy fails. Commit the JSON record (as for v0.10.0) by a follow-up PR.

## 4. Site check after the tag

Pages deploys from `main` on push (`docs.yml` job `docs-deploy`), not from the tag; the version comes from `tools/site_facts.json`.

```bash
gh run list --repo AshJha0/quantforge --workflow docs.yml --branch main --limit 1     # green, includes docs-deploy
curl -fsS https://ashjha0.github.io/quantforge/ | grep -o "1\.0\.0" | head -1          # prints 1.0.0
curl -fsS https://ashjha0.github.io/quantforge/ | grep -c "0\.10\.1"                   # prints 0
```

Also open the release notes page and the known-issues page on the site and confirm every miss listed in `docs/releases/v1.0.0.md` is there. KR-227 counts on `main` come from the Docs run's `site-view` artifact (`gh run download <docs-run-id> -n site-view`).

## 5. After

- Dispatch `mutation-stage.yml` on `main` (the scheduled run did not fire on 2026-11-22) and a fuzz run on `main` (K9-1a closes only on a green one): `gh workflow run mutation-stage.yml --ref main`, `gh workflow run fuzz.yml --ref main`.
- Delete superseded branches (list in `STAGE_K_RESUME.md` session 5 final line) only with the owner's go-ahead.
