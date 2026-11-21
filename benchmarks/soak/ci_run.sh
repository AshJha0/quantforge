#!/usr/bin/env bash
# K-6 CI driver: soak, capacity at 1, 2 and 4 processes, and (Python only, third argument "planted") the two planted
# faults. Every step runs even if an earlier one misses; the job fails at the end if any step missed.
# Usage: ci_run.sh python|java|cpp|rust MINUTES [planted]
set -uo pipefail
impl=$1; minutes=$2; planted=${3:-}
rc=0
step() { echo "::group::$*"; "$@"; local r=$?; echo "::endgroup::"; echo "$* -> exit $r" | tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}"; [ $r -eq 0 ] || rc=1; }
step python3 benchmarks/soak/soak.py --impl "$impl" --minutes "$minutes" --tag ci
step python3 benchmarks/soak/capacity.py --impl "$impl" --procs 1,2,4 --out "benchmarks/results/k6/capacity-$impl-ci.json"
if [ "$planted" = planted ]; then
  step python3 benchmarks/soak/soak.py --impl "$impl" --minutes 20 --tag ci --plant-leak
  step python3 benchmarks/soak/capacity.py --impl "$impl" --plant-wrong --out "benchmarks/results/k6/capacity-$impl-ci-planted-wrong.json"
fi
rm -rf benchmarks/results/k6/.*-work
exit $rc
