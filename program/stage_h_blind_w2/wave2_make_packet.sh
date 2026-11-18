#!/bin/sh
# Usage: wave2_make_packet.sh <quantforge checkout on stage-h> <packet dir> [b]
# Normal packet dir: C:\Work\Claude\institutional-quant-engine-plan\stage_h_blind\wave2_packet
# Builds the wave-2 blind packet: stripped specs (no Expected/Derivation/Check
# columns) plus the rulings files, and a SHA-256 manifest.
# Third argument "b" builds packet 2b instead: dark-pool, smart-order-router
# and paper-trading (dark_h, sor_h, pt_h) with the H-21 rulings added.
set -eu
R="$1"; P="$2"; W="${3:-a}"; D="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$P"
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
