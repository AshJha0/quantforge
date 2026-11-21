# K-8 phase 2: stop note (2026-11-20, laptop shutdown at 23:00 UTC)

## What is complete

The counted run of KR-260 is complete and scored: 120 of 120 cases for the method (201/100) and for the QuantLib reference (8,000/3,201). The raw results were frozen before scoring (`program/k8_phase2/RAW_MANIFEST.json`, combined SHA-256 `ad53af01645f49fd45e3045ac34894b8c9ad3ed17f97bbe661c69cf873b40410`, commit `c3589e58`). Result: recorded MISS, 53 of 120 (`oracle/K8_PHASE2_RESULT.json`; spec `specifications/06-risk/bermudan-ladder-k8.md`, Phase 2 acceptance, Result). Nothing in this note can change that verdict.

## What is partial: the point 5 cross-check (reported, not counted)

The method at 801/400 and 1601/800 on the first case of each nominal cell (10 cases, 20 runs). Done: 2 of 20 (801/400 for k8p2-0001 and k8p2-0013), in `program/k8_phase2/raw/method_801_400/`. **Partial, NOT scored: no comparison of any kind has been computed on these files.** Stopped by hand at about 18:40 UTC because 1601/800 takes about 45 minutes per case on this laptop and would not finish before the shutdown.

## Frozen inputs (must not change on resume)

- `oracle/K8_PHASE2_CASES.json` SHA-256 `0fd9b43bd631202cbc26a5c6e286e1f3ac2c473ba1cdb14709275d977e18f553`
- `oracle/python/k8_phase2_run.py` SHA-256 `520deb58ed0835d0b8ba3612ce312ccdf8c0d0b4e62e0890b5f8b084783478e8`

Check both with `sha256sum` before resuming.

## Resume command (Windows, from the worktree root, project venv)

```
python\.venv\Scripts\python.exe oracle\python\k8_phase2_run.py cross --workers 2
python\.venv\Scripts\python.exe oracle\python\k8_phase2_run.py cross-report
```

The first command skips the two runs whose files exist. Expect about 1 hour for the eight remaining 801/400 runs and 7 to 8 hours of CPU for the ten 1601/800 runs; launch it detached (WMI-launched `.cmd`, as `C:/Work/Claude/qf-wt/_h4ci/k8p/k8p2.cmd`) with a failure watcher. The second command writes `program/k8_phase2/CROSS_CHECK.json`.

Note from this run: `start /low` in the `.cmd` puts the workers at Idle priority, and the runner's own call to lower the priority does not raise them back to below normal; with other lanes running at normal priority the workers were starved for about 40 minutes. Use `start /belownormal` instead.
