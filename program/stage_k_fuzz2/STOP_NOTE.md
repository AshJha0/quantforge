# Stage K fuzz2 lane: stop note

Branch `k-v1-fuzz2` (cut from main 11ba1b40). Worktree C:/Work/Claude/qf-wt/k-v1-fuzz2.

## Done
1. Maven repository cache on every Java job. 14 setup-java jobs already had `cache: maven`; added it to
   release.yml (release-build-java) and tutorial.yml (tutorial-java); lowlat-book.yml has no setup-java, so it
   gets an `actions/cache` step on `~/.m2/repository` (same SHA pin as conformance.yml). Reason: three HTTP 429
   failures from Maven Central on 2026-11-20. YAML parses (read).

## Not done
2. Fuzz findings from run 44815591552 (Java DateTimeException on a huge year; Python TypeError on scalar for list).
3. docs/known-issues.md row K9-1a text.

## How to resume
Read C:/Work/Claude/qf-wt/_h4ci/LANE_RULES_K.md, then continue at item 2.
