# Stop note, lane k-xva-spec (2026-11-20)

Written before the 23:00 UTC shutdown. Repo gates: 0 failures on the pushed head (local laptop, not the acceptance machine); build_site 0 broken links; test_preregs OK. Branch `k-xva-spec`, pushed; no PR (lane rules). `origin/k-v1` was merged in at 2633f416 (one conflict, the generated `specifications/name-map.json`, regenerated).

| Item | State | Evidence |
|---|---|---|
| ORE wheel licence | `open-source-risk-engine` 1.8.17.0, cp312 win_amd64 wheel, sha256 `c34ca87410350c1454f9e356057a77527d68fd2c8097d86674ec3a1d058d0708` (equal to the hash pinned in `oracle/ore/requirements-ore.txt`). METADATA `License:` field and `dist-info/licenses/LICENSE.txt` (sha256 `bace634a...6f06f`, 1,644 bytes): the ORE-SWIG text, three-clause BSD ("Modified BSD"), copyright 2018-2020 Quaternion Risk Management Ltd. and 2021-2022 Acadia Inc. Same conditions as the repository's `license.txt` (copyright years differ). No classifier, no SPDX expression. The wheel was deleted after reading. | read 2026-11-20 (`pip download`, no account) |
| Survival ruling | KR-296 (FCA, FBA, MVA at the bucket start) and KR-297 (ColVA `BOTH` likewise) drafted as PROPOSED and carried into the specs; KR-298 (spec gaps), KR-299 (candidate goldens). No released golden moves. | `specifications/stage-k-rulings-xva.md` |
| Packet v2 | built; MANIFEST.sha256 file hash `2fb743050b478768edc3b8ce71d98ac9b605b093136f2e15820b66c7e8463d6b`; blind run done: **41 MATCH of 41** | `program/STAGE_K_BLIND_XVA.md` "Version 2", `stage_k_blind/xva_v2/` |
| Oracle values | 20 of 20 candidates produced (plus the other 44 non-ORE value cases), 50-digit mpmath | `oracle/xva_k8b_candidates/` (MANIFEST.sha256), `oracle/python/gen_stage_k_xva_k8b.py --check` (about 10 minutes, mostly the WWR gradient) |
| ORE O cases | not run (WSL avoided by the brief) | gate file section 4 |

## Exact next step

1. Coordinator: confirm or reject KR-296 to KR-299. If KR-296/297 are rejected, run `python -I oracle/python/gen_stage_k_xva_k8b.py --convention end` for the old values, set `CONV` default to `end`, regenerate, and rerun packet v2 (mva and colva cases change).
2. Implementation lane (after k-v1-aad lands): implement the K-8b operations in four builds; move each `oracle/xva_k8b_candidates/<suite>.json` into `datasets/golden/stage_k/`, add the suites to `tools/outside_shares.py` `STAGE_K_ITEMS` (K-8b items), add `DR-H2 blind v2 MATCH` to `verified_by` of the 41 matched cases, add error goldens (`*_ke-*`, two errors at once, HR-66), and update hard-coded golden counts in the C++ and Rust tests.
3. MVA and the shock library stay under 60% until ORE runs pass (one `dimModel Flat` case; two shock cases); those need a WSL slot.
