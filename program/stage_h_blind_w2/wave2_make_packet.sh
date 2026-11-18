#!/bin/sh
# Usage: wave2_make_packet.sh <quantforge checkout on stage-h> <packet dir> [b]
# Normal packet dir: C:\Work\Claude\institutional-quant-engine-plan\stage_h_blind\wave2_packet
# Builds the wave-2 blind packet: stripped specs (no Expected/Derivation/Check
# columns) plus the rulings files, and a SHA-256 manifest.
# Third argument "b" builds packet 2b instead: dark-pool, smart-order-router
# and paper-trading (dark_h, sor_h, pt_h) with the H-21 rulings added.
# Third argument "k1" builds the stage K wave-1 packet (see the k1 block).
# Third argument "exec" builds the H-14/H-17 packet: adaptive-algos and
# tca-pretrade (alg_h, tcx_h), inputs-only JSON, the rulings they cite, and
# coordinator/LEAKS.tsv (not for the blind lane; fails on a leak).
set -eu
R="$1"; P="$2"; W="${3:-a}"; D="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$P"
if [ "$W" = k1 ]; then
  # Third argument "k1": stage K wave 1 (bt_k, inc_k, trig_k, idr_k, rich_k). k1_blind.py strips blind:strip
  # blocks and Expected/Check/Why/Derivation columns, keeping the output field names. idr_k-0005 is
  # oracle-pending and stays out. Packet dir: institutional-quant-engine-plan/stage_k_blind/w1_packet. The leak
  # list goes OUTSIDE the packet: python -I k1_blind.py leaks <checkout> <packet> > ../w1_LEAKS.tsv
  PY=python3; "$PY" -c "" >/dev/null 2>&1 || PY=python
  "$PY" -I "$D/k1_blind.py" build "$R" "$P"
  cd "$P"
  sha256sum bitemporal-store.blind.md incremental-update.blind.md recalibration-triggers.blind.md intraday-risk-bounds.blind.md bermudan-ladder-k8.blind.md stage-k-rulings-w1.md > MANIFEST.sha256
  exit 0
fi
if [ "$W" = micro ]; then
  # Third argument "micro": H-4b estimators and H-16 venue analytics with HR-70..74.
  awk -f "$D/wave2_extract.awk" "$R/specifications/09-microstructure/micro-estimators.md" > "$P/micro-estimators.blind.md"
  awk -f "$D/wave2_extract.awk" "$R/specifications/10-execution/venue-analytics.md" > "$P/venue-analytics.blind.md"
  cp "$R/specifications/stage-h-rulings-micro.md" "$P/"
  cd "$P"
  sha256sum micro-estimators.blind.md venue-analytics.blind.md stage-h-rulings-micro.md > MANIFEST.sha256
  exit 0
fi
if [ "$W" = paper2 ]; then
  # Third argument "paper2": H-21 blind packet 2, the pt_h value cases with no blind check yet (list in
  # paper2_blind.py): stripped paper-trading.md (HR-77, HR-78 inside), the paper section of cli-contract.md, the
  # H-21 rulings, and inputs-only JSON. Leak list: paper2_leaks.py, kept outside the packet.
  awk -f "$D/wave2_extract.awk" "$R/specifications/10-execution/paper-trading.md" > "$P/paper-trading.blind.md"
  cp "$R/specifications/stage-h-rulings-h21.md" "$P/"
  PY=python3; "$PY" -c "" >/dev/null 2>&1 || PY=python
  "$PY" -I "$D/paper2_blind.py" "$R" "$P"
  cd "$P"
  sha256sum paper-trading.blind.md paper-cli.blind.md stage-h-rulings-h21.md pt_h.inputs.json > MANIFEST.sha256
  exit 0
fi
if [ "$W" = venue ]; then
  # Third argument "venue": H-16 venue analytics only (fresh blind derivation, output names fixed), with the
  # micro rulings and the exec rulings for HR-66, which HR-75 as amended cites. Leak list: venue_leaks.py, kept
  # outside the packet.
  awk -f "$D/wave2_extract.awk" "$R/specifications/10-execution/venue-analytics.md" > "$P/venue-analytics.blind.md"
  cp "$R/specifications/stage-h-rulings-micro.md" "$R/specifications/stage-h-rulings-w2-exec.md" "$P/"
  PY=python3; "$PY" -c "" >/dev/null 2>&1 || PY=python
  "$PY" -I "$D/venue_redact.py" "$P"
  cd "$P"
  sha256sum venue-analytics.blind.md stage-h-rulings-micro.md stage-h-rulings-w2-exec.md > MANIFEST.sha256
  exit 0
fi
if [ "$W" = exec ]; then
  for f in adaptive-algos tca-pretrade tca schedules; do awk -f "$D/wave2_extract.awk" "$R/specifications/10-execution/$f.md" > "$P/$f.blind.md"; done
  cp "$R/specifications/stage-h-rulings-w1.md" "$R/specifications/stage-h-rulings-h21.md" "$R/specifications/stage-h-rulings-w2-exec.md" "$P/"
  PY=python3; "$PY" -c "" >/dev/null 2>&1 || PY=python
  "$PY" -I "$D/wave2_exec_blind.py" "$R" "$P"
  cd "$P"
  sha256sum adaptive-algos.blind.md tca-pretrade.blind.md tca.blind.md schedules.blind.md stage-h-rulings-w1.md stage-h-rulings-h21.md stage-h-rulings-w2-exec.md alg_h.inputs.json tcx_h.inputs.json > MANIFEST.sha256
  exit 0
fi
if [ "$W" = b ]; then
  S="dark-pool smart-order-router paper-trading"
  for f in $S; do awk -f "$D/wave2_extract.awk" "$R/specifications/10-execution/$f.md" > "$P/$f.blind.md"; done
  cp "$R/specifications/stage-h-rulings-w1.md" "$R/specifications/stage-h-rulings-w1b.md" "$R/specifications/stage-h-rulings-h21.md" "$P/"
  cd "$P"
  sha256sum dark-pool.blind.md smart-order-router.blind.md paper-trading.blind.md stage-h-rulings-w1.md stage-h-rulings-w1b.md stage-h-rulings-h21.md > MANIFEST.sha256
  exit 0
fi
awk -f "$D/wave2_extract.awk" "$R/specifications/09-microstructure/order-book.md" > "$P/order-book.blind.md"
awk -f "$D/wave2_extract.awk" "$R/specifications/10-execution/lit-matching.md" > "$P/lit-matching.blind.md"
cp "$R/specifications/stage-h-rulings-w1.md" "$R/specifications/stage-h-rulings-w1b.md" "$P/"
cd "$P"
sha256sum order-book.blind.md lit-matching.blind.md stage-h-rulings-w1.md stage-h-rulings-w1b.md > MANIFEST.sha256
