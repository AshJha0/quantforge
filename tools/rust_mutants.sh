#!/usr/bin/env bash
# Local cargo-mutants run for the Rust core.
#
# cargo-mutants copies only the cargo workspace (rust/) to a temp dir, but sobol.rs embeds
# specifications/01-core/data/*.json from outside rust/, so the copy build fails. This script
# instead clones the committed tree (HEAD, plus nothing uncommitted) into a scratch directory
# and runs `cargo mutants --in-place` there, so no mutant can ever be left in your checkout.
#
# Usage: tools/rust_mutants.sh '**/credit.rs' [extra cargo-mutants args...]
# Output: <scratch>/repo/rust/mutants.out (path printed at the end). Needs cargo-mutants 27.1.0.
set -euo pipefail
target="${1:?file glob, e.g. '**/credit.rs'}"; shift
root="$(git rev-parse --show-toplevel)"
scratch="${QF_MUTANTS_DIR:-$(mktemp -d)}"
rm -rf "$scratch/repo"
git clone -q --no-hardlinks "$root" "$scratch/repo"
git -C "$scratch/repo" checkout -q "$(git -C "$root" rev-parse HEAD)"
# reuse the existing build cache to save the first full build
export CARGO_TARGET_DIR="${CARGO_TARGET_DIR:-$scratch/target}"
cd "$scratch/repo/rust"
set +e
cargo mutants --in-place -p quantforge-core -f "$target" "$@"
code=$?
echo "results: $scratch/repo/rust/mutants.out (exit $code: 0 all caught, 2 missed, 3 timeouts)"
exit $code
