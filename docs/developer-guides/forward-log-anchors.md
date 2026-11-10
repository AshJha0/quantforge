# Forward-log anchors

Plan 13.2, item R4. The forward log is a hash chain, but anyone who can write to `forward-log` could rewrite an old row and recompute every later hash, and `forward_log.py verify` would still pass. Anchors close that gap: the chain head is stamped with [OpenTimestamps](https://opentimestamps.org) (free, no account, no secret), which ties it to a Bitcoin block the repository owner does not control.

## What the recorder does

After each push to `forward-log`, `.github/workflows/recorder.yml` (step "Anchor the head hash outside the repo"):

1. Verifies the new log against every anchor already held. A mismatch fails the step and the run goes red.
2. Writes `anchors/<UTC time>.json` holding `{count, head, time}` with `tools/forward-log/anchor.py make --stamp`, and stamps it with `ots stamp`, giving `<UTC time>.json.ots`.
3. Runs `ots upgrade` on older proofs, which adds the Bitcoin attestation a few hours after a stamp.
4. Pushes both files to branch `forward-log-anchors`, and tags the `forward-log` commit `forward-log-anchor-<time>` (an annotated tag, unsigned).

The step is soft: if the OpenTimestamps calendars are down, the rows are still pushed and the run is marked failed.

## How to verify

```bash
git fetch origin forward-log forward-log-anchors
git show origin/forward-log:actions/log.jsonl > log.jsonl
git archive origin/forward-log-anchors anchors | tar -x
pip install opentimestamps-client==0.7.2
python tools/forward-log/anchor.py verify --log log.jsonl --anchors anchors --ots
```

Output such as `chain ok, 12 anchors match; OpenTimestamps: 10 confirmed, 2 pending` means:

- The chain is internally consistent.
- For every anchor, line `count` of the log still has hash `head`. Rewriting any earlier line, even with all hashes recomputed, changes that hash; removing lines makes the log shorter than `count`.
- Each `.ots` proof ties the anchor file to Bitcoin. "Pending" proofs are under a day old and become confirmed after `ots upgrade`. `ots verify` needs a Bitcoin Core node or, by default, queries public block explorers.

Without `--ots`, only the first two checks run (offline, standard library only). `python tools/test_tools.py ForwardLogAnchor` is the acceptance test: it rewrites an old line, recomputes every hash, shows `forward_log.py verify` still passes, and shows `anchor.py verify` fails.

An attacker who rewrites the log can also rewrite the anchor JSON files, which is why the `.ots` proofs matter: a changed JSON no longer matches its proof, and a proof cannot be backdated.

## Signed commits on `forward-log`: not enabled

GitHub signs commits made through its own web flows, not those pushed by `GITHUB_TOKEN`. A free route that needs no owner-held key is Sigstore keyless signing with `gitsign` (OIDC identity from the workflow, `id-token: write`). It was not wired in because it cannot be exercised before the first scheduled run, and the OpenTimestamps anchors already give the acceptance property. If wanted later, the owner needs to create nothing: a follow-up adds `gitsign` to the recorder and `gitsign verify` to this guide. A GPG or SSH signing key would need an owner-held secret and is not used.

The annotated tags are unsigned for the same reason; they are a convenience marker, and the trust comes from the `.ots` proofs.
