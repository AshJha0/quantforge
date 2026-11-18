#!/bin/sh
# Usage: wave2_make_packet.sh <quantforge checkout on stage-h> <packet dir>
# Normal packet dir: C:\Work\Claude\institutional-quant-engine-plan\stage_h_blind\wave2_packet
# Builds the wave-2 blind packet: stripped specs (no Expected/Derivation/Check
# columns) plus the rulings files, and a SHA-256 manifest.
set -eu
R="$1"; P="$2"; D="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$P"
awk -f "$D/wave2_extract.awk" "$R/specifications/09-microstructure/order-book.md" > "$P/order-book.blind.md"
awk -f "$D/wave2_extract.awk" "$R/specifications/10-execution/lit-matching.md" > "$P/lit-matching.blind.md"
cp "$R/specifications/stage-h-rulings-w1.md" "$R/specifications/stage-h-rulings-w1b.md" "$P/"
cd "$P"
sha256sum order-book.blind.md lit-matching.blind.md stage-h-rulings-w1.md stage-h-rulings-w1b.md > MANIFEST.sha256
