#!/bin/bash
# H-9 workload R2 and row L7 runner (low-latency-book.md items 2a, 2b, Harness; low-latency-targets.md (f), (g), (h)).
# Run from Git Bash on Windows, at the repository root. C++ and Rust run in WSL (pinned, taskset -c 2, under the
# machine-wide WSL lock); Java runs on native Windows, unpinned, as for R and S.
#
#   benchmarks/h9/run_r2.sh build      build qf_lowlat_book (WSL, Release), lowlat_book (WSL, --release), LowLatBook (Java)
#   benchmarks/h9/run_r2.sh correct    form A correctness in C++, Rust, Java and the Python reference (check_r2.py),
#                                      counts compared field by field; form B (L7 input) dumps checked by check_r.py;
#                                      writes $OUT/correct/R2_correctness.ok only if everything passes
#   benchmarks/h9/run_r2.sh time [--skip-l7]
#                                      timing in stages, in priority order r2-cpp, r2-rust, r2-java, l7 (STAGES="..."
#                                      picks and orders them); $RUNS runs each. Each stage writes complete result files
#                                      (temporary name, stamped, renamed) and then a marker; a rerun skips completed
#                                      stages, so a stop leaves valid files for the stages that finished. Refuses unless
#                                      the correctness marker exists for the same input hashes and the same commit.
#                                      Uses the QUIET flag if it is already set (the coordinator's), else sets it.
#   benchmarks/h9/run_r2.sh all        correct, then time
# `correct` starts the Python reference for both symbols at once (PY_JOBS workers each, default 5) while the harness
# passes run, and reuses a finished reference output on a rerun.
#
# Inputs: $R2DIR (default /c/Work/Claude/qf-h9-r2) holds the output of `build_r2.py auto`. Every run first checks the
# inputs against the COMMITTED benchmarks/results/h9/R2_replay.sha256 (refuses if that file is missing, not
# committed, changed, or does not match). Results: $OUT (default benchmarks/results/h9): cpp_R2_<SYM>.json,
# rust_R2_*, java_R2_*, cpp_L7_<SYM>.json, rust_L7_*, java_L7_*, each with the publication fields of targets (f) and
# the load average at the start and end of every run. Logs, GC logs and JFR files go to $R2DIR/logs.
# While timing runs, the QUIET flag (/c/Work/Claude/qf-wt/_h4ci/QUIET) is set, so other lanes start nothing heavy.
#
# SMOKE=1 (development only): the hash file may be uncommitted (R2_HASHES, default $R2DIR/R2_replay.sha256), OUT must
# lie outside the repository, the warm-up is QF_SMOKE_WARMUP (default 1000) messages, and RUNS defaults to 1. A smoke
# figure is never a result.
set -euo pipefail

MODE=${1:-}
SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
REPO="$(cd "$(dirname "$SELF")/../.." && pwd)"
SYMS=${SYMS:-"BTC-USD ETH-USD"}
QUIET_FLAG=/c/Work/Claude/qf-wt/_h4ci/QUIET
# Targets commits stamped into every result: fa020dd8 (low-latency-targets.md, before any H-9 timing, 2026-11-18) and
# f2d90738 (sections (g) and (h), before any R2 timing, 2026-11-19, HR-130 and HR-131).

wslpath_of() { echo "$1" | sed -E 's#^/([a-zA-Z])/#/mnt/\L\1/#'; }

# ------------------------------------------------------------------ WSL side (called through wsl.exe)
if [ "$MODE" = wsl-build ]; then
  SRC=$2
  export CARGO_TARGET_DIR=~/qf-target-r2 PATH=$HOME/.cargo/bin:$HOME/.local/bin:$PATH
  exec 9>~/qf-wsl.lock; flock 9
  rsync -a --delete --exclude .git --exclude target --exclude .venv --exclude 'cpp26/build*' --exclude node_modules "$SRC/" ~/wt-r2/
  cmake -S ~/wt-r2/cpp26 -B ~/bld-r2 -G Ninja -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=OFF -DQF_LOWLAT_BENCH=ON > ~/bld-r2.cfg.log
  cmake --build ~/bld-r2 --parallel 6 --target qf_lowlat_book
  (cd ~/wt-r2/rust && cargo build --release -p quantforge-bench --bin lowlat_book)
  { echo "gxx=$(g++ --version | head -1)"; echo "rustc=$(rustc --version)"; } > ~/r2-build.txt
  exit 0
fi
if [ "$MODE" = wsl-run ]; then
  # wsl-run LANG FILE RUNS OUT [K=V ...]: one harness process, pinned to core 2, under the WSL lock.
  LANG_=$2; FILE=$3; NRUNS=$4; RES=$5; shift 5
  for kv in "$@"; do export "$kv"; done
  exec 9>~/qf-wsl.lock; flock 9
  case $LANG_ in
    cpp) BIN=~/bld-r2/qf_lowlat_book; exec taskset -c 2 "$BIN" run "$FILE" "$NRUNS" "$RES" ;;
    rust) exec taskset -c 2 ~/qf-target-r2/release/lowlat_book "$FILE" "$NRUNS" "$RES" ;;
  esac
  exit 64
fi
if [ "$MODE" = wsl-facts ]; then
  echo "{\"cpu\": \"$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | sed 's/^ //')\", \"logical_cpus\": $(nproc),"\
       "\"ram_kb_wsl\": $(awk '/MemTotal/ {print $2}' /proc/meminfo), \"kernel\": \"$(uname -r)\","\
       "\"governor\": \"$(cat /sys/devices/system/cpu/cpu2/cpufreq/scaling_governor 2>/dev/null || echo 'not exposed in WSL')\","\
       "\"gxx\": \"$(grep gxx= ~/r2-build.txt | cut -d= -f2-)\", \"rustc\": \"$(grep rustc= ~/r2-build.txt | cut -d= -f2-)\"}"
  exit 0
fi

# ------------------------------------------------------------------ Windows side
R2DIR=${R2DIR:-/c/Work/Claude/qf-h9-r2}
SMOKE=${SMOKE:-0}
OUT=${OUT:-$REPO/benchmarks/results/h9}
RUNS=${RUNS:-$([ "$SMOKE" = 1 ] && echo 1 || echo 5)}
export PATH="/c/Users/ashis/tools/apache-maven-3.9.9/bin:$PATH" JAVA_HOME="${JAVA_HOME:-/c/Program Files/Eclipse Adoptium/jdk-25.0.5.8-hotspot}"
JAVA="$JAVA_HOME/bin/java"
JFLAGS="-Xms2g -Xmx2g -XX:+AlwaysPreTouch"
LOGS=$R2DIR/logs
mkdir -p "$LOGS"

say() { echo "[run_r2 $(date -u +%H:%M:%S)] $*"; }
die() { say "REFUSED: $*" >&2; exit 3; }

hash_file() {
  if [ "$SMOKE" = 1 ]; then
    case "$(cd "$OUT" 2>/dev/null && pwd || echo "$OUT")" in "$REPO"*) die "SMOKE=1 needs OUT outside the repository" ;; esac
    echo "${R2_HASHES:-$R2DIR/R2_replay.sha256}"
  else
    echo "$REPO/benchmarks/results/h9/R2_replay.sha256"
  fi
}

check_hashes() {
  # HR-134, HR-135 (audit KA-B6): outside SMOKE=1, an input built with --sample-only, --tolerant, --after, --until,
  # --min-hours or --max-hours (stamped in R2_window.json, whose hash is in R2_replay.sha256) is refused before
  # anything else, so it can give neither a correctness marker nor a timing result.
  if [ "$SMOKE" != 1 ]; then
    python -I "$REPO/benchmarks/h9/r2_meta.py" inputs "$R2DIR" >&2 || die "input not built under the HR-134 rule (see above)"
  fi
  local H; H=$(hash_file) || exit 3
  [ -f "$H" ] || die "input hash file $H is missing (commit build_r2.py's R2_replay.sha256 there first)"
  if [ "$SMOKE" != 1 ]; then
    git -C "$REPO" ls-files --error-unmatch benchmarks/results/h9/R2_replay.sha256 > /dev/null 2>&1 || die "R2_replay.sha256 is not committed"
    git -C "$REPO" diff --quiet HEAD -- benchmarks/results/h9/R2_replay.sha256 || die "R2_replay.sha256 differs from the committed one"
  fi
  (cd "$R2DIR" && sha256sum --strict --quiet -c "$H") || die "inputs in $R2DIR do not match $H"
  say "inputs match $(basename "$H") ($(wc -l < "$H") files)"
}

meta_field() { python -I -c "import json,sys; m=json.load(open(sys.argv[1])); print(eval('m'+sys.argv[2]))" "$R2DIR/R2_$1.meta.json" "$2"; }

java_run() {  # java_run FILE RUNS OUT LOGTAG [K=V ...]
  local f=$1 n=$2 o=$3 tag=$4; shift 4
  ( for kv in "$@"; do export "$kv"; done
    cd "$REPO/java25" && "$JAVA" $JFLAGS -cp "target/classes;target/lowlat" -Xlog:gc:file="$(cygpath -m "$LOGS/gc_$tag.log")" \
      -XX:StartFlightRecording=filename="$(cygpath -m "$LOGS/$tag.jfr")",settings=profile \
      org.quantforge.bench.LowLatBook "$(cygpath -m "$f")" "$n" "$(cygpath -m "$o")" ) 2> "$LOGS/java_$tag.err"
}

wsl_run() {  # wsl_run LANG FILE RUNS OUT LOGTAG [K=V ...]
  local l=$1 f=$2 n=$3 o=$4 tag=$5; shift 5
  MSYS2_ARG_CONV_EXCL="*" wsl.exe -e bash "$(wslpath_of "$SELF")" wsl-run "$l" "$(wslpath_of "$f")" "$n" "$(wslpath_of "$o")" "$@" 2> "$LOGS/${l}_$tag.err"
}

warmup_of() {  # warmup_of SYM r2|l7
  if [ "$SMOKE" = 1 ]; then echo "${QF_SMOKE_WARMUP:-1000}"; return; fi
  if [ "$2" = r2 ]; then meta_field "$1" '["warmup_messages"]'; else meta_field "$1" '["form_b"]["warmup_messages"]'; fi
}

do_build() {
  say "build: C++ and Rust in WSL (Release; --release), Java on Windows"
  MSYS2_ARG_CONV_EXCL="*" wsl.exe -e bash "$(wslpath_of "$SELF")" wsl-build "$(wslpath_of "$REPO")"
  local LOCK=/c/Work/Claude/qf-wt/_h4ci/mvn.lock.d  # one Maven run at a time on the machine (Git Bash has no flock)
  until mkdir "$LOCK" 2> /dev/null; do say "waiting for the Maven lock"; sleep 20; done
  (cd "$REPO/java25" && mvn -B -q -DskipTests compile && mkdir -p target/lowlat && \
     "$JAVA_HOME/bin/javac" -d target/lowlat -cp target/classes src/jmh/java/org/quantforge/bench/LowLatBook.java) \
     || { rmdir "$LOCK"; exit 1; }
  rmdir "$LOCK"
  say "build done"
}

replay_sha() { sha256sum < "$(hash_file)" | cut -d' ' -f1; }
stage_key() { echo "replay_hashes_sha256=$(replay_sha) commit=$(git -C "$REPO" rev-parse HEAD) runs=$RUNS smoke=$SMOKE"; }
stage_done() { [ -f "$1" ] && [ "$(cat "$1")" = "$(stage_key)" ]; }   # stage_done MARKER

do_correct() {
  check_hashes
  local C=$OUT/correct; mkdir -p "$C"; rm -f "$C/R2_correctness.ok"
  local fail=0 s
  # 1. The Python reference for both symbols, in parallel (one process per symbol, PY_JOBS workers each), started
  #    first because it is the long pole; each output is reused on a resumed run if its marker matches.
  local pids=()
  for s in $SYMS; do
    if stage_done "$C/py_R2_$s.done"; then say "$s Python reference: reusing $C/py_R2_$s.json"; continue; fi
    say "$s Python reference started (background, ${PY_JOBS:-5} workers)"
    ( cd "$REPO/python" && uv run --locked python ../benchmarks/h9/check_r2.py "$R2DIR/R2_$s" --jobs "${PY_JOBS:-5}" \
        --out "$C/py_R2_$s.json" > "$LOGS/py_R2_$s.log" 2>&1; rc=$?
      [ $rc -le 2 ] && [ -s "$C/py_R2_$s.json" ] && stage_key > "$C/py_R2_$s.done"; exit $rc ) &
    pids+=($!)
  done
  # 2. Harness form A passes (0 timed runs) and the L7 dumps, meanwhile.
  for s in $SYMS; do
    local PD; PD=$(meta_field "$s" '["price_decimals"]')
    say "$s R2 form A: C++, Rust, Java (runs 0: correctness only)"
    for l in cpp rust; do
      wsl_run $l "$R2DIR/R2_$s.bin" 0 "$C/${l}_R2_$s.json" "R2c_$s" QF_H9_WORKLOAD=R2 \
        QF_H9_CHECKPOINTS="$(wslpath_of "$R2DIR/R2_$s.cps.bin")" || { say "$l R2 $s correctness exit $?"; fail=1; }
    done
    java_run "$R2DIR/R2_$s.bin" 0 "$C/java_R2_$s.json" "R2c_$s" QF_H9_WORKLOAD=R2 \
      QF_H9_CHECKPOINTS="$(cygpath -m "$R2DIR/R2_$s.cps.bin")" || { say "java R2 $s correctness exit $?"; fail=1; }
    say "$s L7 input (form B): top(100) dumps in each language, checked by check_r.py against micro.book.rebuild"
    for l in cpp rust; do
      wsl_run $l "$R2DIR/L7_$s.bin" 0 "$C/${l}_L7_$s.json" "L7c_$s" QF_H9_WORKLOAD=L7 \
        QF_H9_DUMP="$(wslpath_of "$LOGS/dump_${l}_L7_$s.txt")" || { say "$l L7 $s exit $?"; fail=1; }
    done
    java_run "$R2DIR/L7_$s.bin" 0 "$C/java_L7_$s.json" "L7c_$s" QF_H9_WORKLOAD=L7 \
      QF_H9_DUMP="$(cygpath -m "$LOGS/dump_java_L7_$s.txt")" || { say "java L7 $s exit $?"; fail=1; }
    cmp -s "$LOGS/dump_cpp_L7_$s.txt" "$LOGS/dump_rust_L7_$s.txt" && cmp -s "$LOGS/dump_cpp_L7_$s.txt" "$LOGS/dump_java_L7_$s.txt" \
      || { say "$s L7 dumps differ between languages"; fail=1; }
    (cd "$REPO/python" && uv run --locked python ../benchmarks/h9/check_r.py "$R2DIR/L7_$s" "$LOGS/dump_cpp_L7_$s.txt" "$PD") \
      > "$C/py_L7_$s.json" 2> "$LOGS/py_L7_$s.err" || { say "$s L7 check_r.py failed"; fail=1; }
  done
  # 3. Wait for the reference, then compare the four sets of counts per symbol.
  local p; for p in "${pids[@]}"; do wait "$p" || true; done   # judged by the comparison below
  for s in $SYMS; do
    local rc=0
    python -I "$REPO/benchmarks/h9/r2_meta.py" compare "$s" "$C/py_R2_$s.json" "$C/cpp_R2_$s.json" "$C/rust_R2_$s.json" \
      "$C/java_R2_$s.json" || rc=$?
    [ $rc -eq 0 ] || { say "$s R2 form A: compare exit $rc"; fail=1; }
  done
  if [ $fail -ne 0 ]; then say "CORRECTNESS FAILED: no timing will run"; exit 1; fi
  { echo "replay_hashes_sha256=$(replay_sha)"; echo "commit=$(git -C "$REPO" rev-parse HEAD)";
    echo "below10_venue_side=${QF_R2_BELOW10_VENUE_SIDE:-0}"; echo "at=$(date -u +%FT%TZ)"; } > "$C/R2_correctness.ok"
  say "correctness passed in every language: $C/R2_correctness.ok"
}

write_publication() {  # write_publication META
  local WF; WF=$(MSYS2_ARG_CONV_EXCL="*" wsl.exe -e bash "$(wslpath_of "$SELF")" wsl-facts)
  local JV; JV=$("$JAVA" -version 2>&1 | head -1)
  python -I - "$1" "$WF" "$(hash_file)" "$RUNS" "$(git -C "$REPO" rev-parse HEAD)" "$SMOKE" "$JV" <<'PY'
import json, platform, sys
out, wf, hashes, runs, commit, smoke, jv = sys.argv[1:]
wf = json.loads(wf)
meta = {
    "machine": {"cpu": wf["cpu"], "logical_cpus": wf["logical_cpus"], "ram_wsl_kb": wf["ram_kb_wsl"],
                "frequency_governor": wf["governor"]},
    "commit": commit, "repeats": int(runs),
    "targets_commits": {"L1-L6": "fa020dd8", "L1-R2 to L3-R2 and L7": "f2d90738"},
    "rulings": ["HR-130", "HR-131", "HR-132", "HR-133", "HR-134", "HR-135"],
    "workload_hashes": dict(reversed(l.split()) for l in open(hashes) if l.strip()),
    "labels": ["in-process, simulated feed; no network or venue latency", "crypto venue; not equities or rates",
               "R2: raw venue messages; L7: snapshot-differenced stream (form B), per-level samples",
               "local laptop, not the acceptance machine"],
    "smoke": smoke == "1",
    "languages": {
        "cpp": {"os": "Linux (WSL 2) " + wf["kernel"], "pinned": "taskset -c 2", "compiler": wf["gxx"],
                "flags": "CMake Release (-O3), no -march, -ffp-contract=off"},
        "rust": {"os": "Linux (WSL 2) " + wf["kernel"], "pinned": "taskset -c 2", "compiler": wf["rustc"],
                 "flags": "--release, workspace default profile (no LTO)"},
        "java": {"os": platform.platform(), "pinned": "no (native Windows, unpinned)", "runtime": jv,
                 "flags": "-Xms2g -Xmx2g -XX:+AlwaysPreTouch, G1, JFR settings=profile, -Xlog:gc",
                 "load_average_note": "Windows has no load average: loadavg_1m_* is -1; cpu_load_* is getCpuLoad()"},
    },
}
json.dump(meta, open(out, "w"), indent=1)
PY
}

# One timing stage: r2-cpp, r2-rust, r2-java or l7 (all three languages on the form B stream). Each result file is
# written to a temporary name, stamped with the publication fields, then renamed, so a stopped run leaves only
# complete files; the stage marker is written last, and a stage whose marker matches is skipped on a rerun.
run_stage() {
  local st=$1 META=$2 T=$OUT/timing; mkdir -p "$T"
  if stage_done "$T/$st.done"; then say "stage $st already complete for these inputs and commit: skipped"; return 0; fi
  local s l w files=()
  for s in $SYMS; do
    local W2 W7; W2=$(warmup_of "$s" r2); W7=$(warmup_of "$s" l7)
    case $st in
      r2-cpp|r2-rust)
        l=${st#r2-}; say "$st $s: $RUNS runs, warm-up $W2 messages"
        wsl_run $l "$R2DIR/R2_$s.bin" "$RUNS" "$OUT/${l}_R2_$s.json.tmp" "R2_$s" QF_H9_WORKLOAD=R2 QF_H9_WARMUP="$W2" \
          QF_H9_CHECKPOINTS="$(wslpath_of "$R2DIR/R2_$s.cps.bin")"
        files+=("$OUT/${l}_R2_$s.json") ;;
      r2-java)
        say "$st $s: $RUNS runs, warm-up $W2 messages"
        java_run "$R2DIR/R2_$s.bin" "$RUNS" "$OUT/java_R2_$s.json.tmp" "R2_$s" QF_H9_WORKLOAD=R2 QF_H9_WARMUP="$W2" \
          QF_H9_CHECKPOINTS="$(cygpath -m "$R2DIR/R2_$s.cps.bin")"
        files+=("$OUT/java_R2_$s.json") ;;
      l7)
        say "$st $s: $RUNS runs per language, warm-up $W7 messages"
        for l in cpp rust; do
          wsl_run $l "$R2DIR/L7_$s.bin" "$RUNS" "$OUT/${l}_L7_$s.json.tmp" "L7_$s" QF_H9_WORKLOAD=L7 QF_H9_WARMUP="$W7" QF_H9_PER_LEVEL=1
          files+=("$OUT/${l}_L7_$s.json")
        done
        java_run "$R2DIR/L7_$s.bin" "$RUNS" "$OUT/java_L7_$s.json.tmp" "L7_$s" QF_H9_WORKLOAD=L7 QF_H9_WARMUP="$W7" QF_H9_PER_LEVEL=1
        files+=("$OUT/java_L7_$s.json") ;;
      *) die "unknown stage $st (r2-cpp, r2-rust, r2-java, l7)" ;;
    esac
  done
  local f
  for f in "${files[@]}"; do
    python -I "$REPO/benchmarks/h9/r2_meta.py" stamp "$f.tmp" "$META"
    mv -f "$f.tmp" "$f"
  done
  stage_key > "$T/$st.done"
  say "stage $st complete: ${files[*]##*/}"
}

do_time() {
  check_hashes
  local C=$OUT/correct
  [ -f "$C/R2_correctness.ok" ] || die "no correctness marker: run 'correct' first"
  grep -q "replay_hashes_sha256=$(replay_sha)" "$C/R2_correctness.ok" || die "the correctness marker is for other inputs"
  grep -q "commit=$(git -C "$REPO" rev-parse HEAD)" "$C/R2_correctness.ok" || die "the correctness marker is for another commit"
  if [ "$SMOKE" != 1 ] && [ ! -e "$QUIET_FLAG" ]; then touch "$QUIET_FLAG"; trap 'rm -f "$QUIET_FLAG"' EXIT; fi
  local META=$LOGS/publication.json
  write_publication "$META"
  local stages=${STAGES:-"r2-cpp r2-rust r2-java l7"}
  [ "${SKIP_L7:-0}" = 1 ] && stages=${stages//l7/}
  local st; for st in $stages; do run_stage "$st" "$META"; done
  say "timing done for stages: $stages"
}

case $MODE in
  build) do_build ;;
  correct) do_correct ;;
  time) shift; for a in "$@"; do [ "$a" = --skip-l7 ] && SKIP_L7=1; done; do_time ;;
  all) do_correct && do_time ;;
  *) sed -n '2,32p' "$SELF"; exit 64 ;;
esac
