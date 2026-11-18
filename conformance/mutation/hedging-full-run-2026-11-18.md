# hedging.cpp full mutation run, 2026-11-18

## Run

- File: `cpp26/src/core/hedging.cpp`, unchanged since 311c914d.
- Generator: `conformance/mutation/cpp_mutants.py`, seed 1, all 947 sites, `--unit`.
- Kill check: golden suite `hedge*_[ij]` plus the unit tests.
- Raw logs (`full.log` mutants 1-237, `full3.log` 238-521, `full4.log` 522-947) and the survivor list are kept outside the repository with the run evidence; every survivor is listed in the table below.

## Counts

| | Count |
|---|---|
| Killed (golden 572, unit 271) | 843 |
| Survived | 100 |
| Did not build | 4 |
| Score, killed / built | 843 / 943 = 89.4 % |
| Score with the ten new kill tests | 853 / 943 = 90.5 % |
| Pre-fix full run, for comparison | 701 / 825 = 85.0 % |

Mutant 521 (`i <= targets.size()`, line 1605) was first listed as a no-build. Its build had been interrupted; re-run
alone it builds and the golden suite kills it. It is counted as killed above.

The four no-builds are genuine compile failures: each turns a `std::string + const char*` concatenation in the
error helpers (lines 26 and 29; mutants 243, 378, 776, 921) into `-`, and `std::string` has no `operator-`.

Line numbers in `equivalents-cpp.md` rows from the pre-fix run have drifted; survivors were matched to them by code
and operator.

## Survivors by class

| Class | Count |
|---|---|
| Accepted (new row) | 27 |
| Equivalent (new row) | 2 |
| Existing row | 61 |
| Killed-by-new-test | 10 |

The new kill tests are in `cpp26/tests/test_hedge_solvers_units.cpp`, tag `[fullrun]`. Confirmed 2026-11-18 in WSL
(gcc, Release): the unit suite passes (523 test cases), and each of the ten mutants (702, 154, 757, 843, 704, 183,
839, 110, 880, 579), re-run alone with `--seed 1 --start k --max k`, is killed by the unit tests.

With those ten kills the score is 853 / 943 = 90.5 %. The 2 new Equivalent rows and the 27 Accepted rows are
counted as survivors: Equivalent rows are left out of samples only after a second reviewer signs them, and the
owner decided on 2026-11-18 that there is no second review.
Expected values are closed forms worked by hand, or the exact minimum 0 of the square nonsingular ns2 data.

Most new Accepted rows are in `refine_face` and `refine_relaxed`. Both are polishing steps that keep a step only
while f falls inside the bounds and active rows, so a mutant there can only skip or shorten the polish. That moves
the output beyond rounding only on near-singular data, and only when the term the mutant touches (a ridge, a
spread, a one-sided active bound, a non-axis equality) is also present. Second-reviewer cells are empty.

## All 100 survivors

| Mutant | Line | Mutated line | Class | Pointer |
|---|---|---|---|---|
| 4 | 1359 | `double g = diag[j] * x[j] - lin[j];` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 36 | 949 | `if (!best \|\| f <= best_f) {` | Existing row | equivalents-cpp.md line 153 |
| 38 | 1160 | `if (next < radius_) visit(i, next);` | Existing row | equivalents-cpp.md line 81 |
| 39 | 1374 | `for (std::size_t j = 0; j < n; ++j) scale += std::fabs(c[i][j] / trial[j]);` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 53 | 632 | `for (std::size_t c = 0; c <= allowed; ++c)` | Existing row | equivalents-cpp.md line 139 |
| 65 | 1370 | `if (trial[j] < lo[j] \|\| trial[j] >= hi[j]) return;` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 78 | 666 | `if (c >= cols && tab[rows][c] == 0.0) continue;` | Existing row | equivalents-cpp.md line 182 |
| 80 | 1380 | `if (!(f <= best)) return;` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 110 | 866 | `if (sign_[j] <= 0) hi[j] = std::min(hi[j], 0.0);` | Killed-by-new-test | "hsu near-singular refinement survives zero-cost instruments, small weights and a small row" |
| 123 | 537 | `for (int sweep = 0; sweep <= 100; ++sweep) {` | Existing row | equivalents-cpp.md line 134 |
| 132 | 331 | `if (t2 < t1) {` | Existing row | equivalents-cpp.md line 119 |
| 138 | 160 | `const double alpha = m[j][j] >= 0.0 ? -norm : norm;` | Existing row | equivalents-cpp.md line 117 |
| 149 | 640 | `if (best == rows \|\| ratio < best_ratio \|\| (ratio == best_ratio && basis[r] <= basis[best])` | Existing row | equivalents-cpp.md line 63 |
| 154 | 868 | `if (p_.impact) diag[j] += cost_weight / (*p_.impact)[j];  // impact counts like a ridge (I` | Killed-by-new-test | "hsu impact on the sign-state path is refined with cost_weight times impact" |
| 160 | 795 | `if ((sign_[j] > 0 && !lo[j]) \|\| (sign_[j] < 0 \|\| !up[j])) ++sign_rows;` | Existing row | equivalents-cpp.md line 75 |
| 174 | 1359 | `double g = diag[j] / x[j] + lin[j];` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 183 | 869 | `lin[j] = k[j] / double(sign_[j]);` | Killed-by-new-test | "hsu near-singular refinement survives zero-cost instruments, small weights and a small row" |
| 195 | 1080 | `fixed[j] = mult.lower_active.empty() ? 0 : char(mult.lower_active[j] && mult.upper_active[` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 208 | 819 | `long long constraints = (long long)(n_ - (ns_.z.empty() ? 0 : ns_.z.front().size())) - (ma` | Existing row | equivalents-cpp.md line 146 |
| 223 | 637 | `for (std::size_t r = 0; r <= rows; ++r) {` | Existing row | equivalents-cpp.md line 73 |
| 236 | 1213 | `for (int iter = 0; iter <= 64; ++iter) {` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 238 | 210 | `for (std::size_t a = 0; a <= r; ++a)  // exact symmetry for the eigen-solver` | Existing row | equivalents-cpp.md line 26 |
| 255 | 1313 | `if (norm >= pick_norm) {` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 263 | 795 | `if ((sign_[j] >= 0 && !lo[j]) \|\| (sign_[j] < 0 && !up[j])) ++sign_rows;` | Existing row | equivalents-cpp.md line 144 |
| 275 | 315 | `if (gap >= certificate * tol) return false;  // no feasible point` | Existing row | equivalents-cpp.md line 171 |
| 291 | 294 | `if (r[k] > r_cut && u_[k] / r[k] <= t1) {` | Existing row | equivalents-cpp.md line 169 |
| 305 | 751 | `if (!lower.empty() && lower[j] && *lower[j] > 0.0) sign_[j] = 1;` | Existing row | equivalents-cpp.md line 183 |
| 306 | 1378 | `if (row && !row_active && dot(*row, trial) >= row_cap) return;` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 325 | 819 | `long long constraints = (long long)(n_ + (ns_.z.empty() ? 0 : ns_.z.front().size())) + (ma` | Existing row | equivalents-cpp.md line 99 |
| 332 | 1227 | `if (trial[j] <= lo[j] \|\| trial[j] > hi[j]) return best;` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 334 | 1227 | `if (trial[j] < lo[j] && trial[j] > hi[j]) return best;` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 352 | 1227 | `if (trial[j] < lo[j] \|\| trial[j] >= hi[j]) return best;` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 368 | 281 | `const bool step_in_primal = d2 >= 1e-24 * dall;` | Existing row | equivalents-cpp.md line 197 |
| 372 | 795 | `if ((sign_[j] > 0 && !lo[j]) \|\| (sign_[j] <= 0 && !up[j])) ++sign_rows;` | Existing row | equivalents-cpp.md line 143 |
| 377 | 211 | `for (std::size_t c = a - 1; c < r; ++c) out[a][c] = out[c][a] = 0.5 * (out[a][c] + out[c][` | Existing row | equivalents-cpp.md line 132 |
| 385 | 1339 | `for (std::size_t k = 0; k <= j; ++k) piv -= l[j][k] * l[j][k];` | Equivalent (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 391 | 1350 | `for (std::size_t j = 0; j < n; ++j) f += diag[j] * v[j] * v[j] - 2.0 * lin[j] * v[j];` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 405 | 1272 | `for (std::size_t i = 0; i < p; ++i) defect[i] = std::fabs(dot(c[i], x) + d[i]);` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 416 | 1417 | `if (eig.front() < singular_threshold * largest_abs(eig))` | Existing row | equivalents-cpp.md line 65 |
| 418 | 106 | `for (std::size_t k = 0; k <= j; ++k) s -= l[i][k] * l[j][k];` | Existing row | equivalents-cpp.md line 121 |
| 434 | 1152 | `if (room <= 0.0) return;` | Existing row | equivalents-cpp.md line 156 |
| 436 | 1340 | `if (!(piv >= 0.0)) return;  // not numerically positive definite: keep the active-set answ` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 437 | 1470 | `for (std::size_t j = 0; j < n; ++j) out.x[j] = p.lot_sizes[j] * double(out.lots[j]) - 0.0;` | Existing row | equivalents-cpp.md line 114 |
| 438 | 873 | `margined_ ? &row : nullptr, limit_, with_margin \|\| mult.general_active, fixed, lo, hi, x);` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 442 | 1456 | `for (const long long x : v) s += x <= 0 ? -x : x;` | Existing row | equivalents-cpp.md line 29 |
| 450 | 546 | `const double t = std::fabs(theta) >= 1e150 ? 0.5 / theta` | Existing row | equivalents-cpp.md line 177 |
| 455 | 1354 | `for (int iter = 0; iter <= 64; ++iter) {` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 456 | 815 | `for (const std::size_t j : free_) sign_[j] = smooth[j] <= 0.0 ? -1 : 1;` | Existing row | equivalents-cpp.md line 145 |
| 462 | 1230 | `if (!(f <= best)) return best;` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 480 | 1375 | `if (std::fabs(dot(c[i], trial) - d[i]) >= std::max(defect[i], std::numeric_limits<double>:` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 510 | 1433 | `for (std::size_t i = 0; i <= n; ++i)` | Existing row | equivalents-cpp.md line 122 |
| 524 | 541 | `if (off < 1e-34 * total \|\| off == 0.0) break;` | Existing row | equivalents-cpp.md line 62 |
| 534 | 270 | `if (step > max_steps) break;` | Existing row | equivalents-cpp.md line 118 |
| 535 | 910 | `const bool up_neg = !upper.empty() && upper[j] && *upper[j] < 0.0;` | Existing row | equivalents-cpp.md line 64 |
| 551 | 630 | `for (std::size_t it = 0; it <= 50 * (rows + cols) + 100; ++it) {` | Existing row | equivalents-cpp.md line 100 |
| 557 | 251 | `const auto max_steps = std::size_t(detail::effort_cap(10 * (long long)(n_ + normals_.size(` | Existing row | equivalents-cpp.md line 133 |
| 559 | 539 | `for (std::size_t p = 0; p <= n; ++p)` | Existing row | equivalents-cpp.md line 135 |
| 564 | 1463 | `(weight(c.lots) == weight(pick->lots) && c.lots <= pick->lots))` | Existing row | equivalents-cpp.md line 160 |
| 571 | 1515 | `for (std::size_t j = 0; j <= i; ++j)` | Existing row | equivalents-cpp.md line 66 |
| 578 | 1169 | `radius_ = std::min(radius_, distance + 1e-9 * (distance + slack_scale_) - 1e-300);` | Existing row | equivalents-cpp.md line 82 |
| 579 | 1294 | `if (norm > 1e-12 / norm0) {` | Killed-by-new-test | "hsu near-singular refinement survives zero-cost instruments, small weights and a small row" |
| 612 | 1439 | `for (std::size_t i = 0; i <= n; ++i) {` | Existing row | equivalents-cpp.md line 123 |
| 625 | 1727 | `for (std::size_t j = 0; j <= i; ++j)` | Existing row | equivalents-cpp.md line 96 |
| 639 | 378 | `if (cc <= 0.0) {` | Existing row | equivalents-cpp.md line 97 |
| 642 | 795 | `if ((sign_[j] > 0 \|\| !lo[j]) \|\| (sign_[j] < 0 && !up[j])) ++sign_rows;` | Existing row | equivalents-cpp.md line 120 |
| 643 | 1294 | `if (norm >= 1e-12 * norm0) {` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 649 | 1782 | `if (eig.front() < singular_threshold * largest_abs(eig))` | Existing row | equivalents-cpp.md line 163 |
| 666 | 1543 | `for (std::size_t m = 0; m <= i; ++m) s -= l[i][m] * w[m];` | Existing row | equivalents-cpp.md line 67 |
| 668 | 1218 | `double acc = diag[j] / nc[j];` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 700 | 1344 | `for (std::size_t k = 0; k <= j; ++k) s -= l[i][k] * l[j][k];` | Equivalent (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 702 | 1079 | `if (p.impact) diag[j] += cost_weight / (*p.impact)[j];  // impact counts like a ridge (I-2` | Killed-by-new-test | "hsu impact on the equality path is refined with cost_weight times impact" |
| 704 | 1413 | `for (std::size_t j = 0; j < n; ++j) ok = ok \|\| std::isfinite(q.h[i][j]);` | Killed-by-new-test | "hsu integer normal equations overflowing in H alone are E_NON_FINITE" |
| 715 | 1280 | `for (int pass = 0; pass <= 2; ++pass)` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 719 | 261 | `if (s < -tolerance(i) && s <= worst) {` | Existing row | equivalents-cpp.md line 166 |
| 729 | 994 | `const bool costed = p.half_spreads \|\| p.impact \|\| p.cost_weight \|\| p.margin_rates && p.mar` | Existing row | equivalents-cpp.md line 193 |
| 737 | 1375 | `if (std::fabs(dot(c[i], trial) - d[i]) > std::max(defect[i], std::numeric_limits<double>::` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 750 | 542 | `for (std::size_t p = 0; p <= n; ++p)` | Existing row | equivalents-cpp.md line 136 |
| 756 | 184 | `for (std::size_t j = 0; j <= i; ++j) s -= m[j][i] * w[j];` | Existing row | equivalents-cpp.md line 165 |
| 757 | 1408 | `for (std::size_t j = 0; j < n; ++j) q.h[j][j] += p.ridge / p.lot_sizes[j] * p.lot_sizes[j]` | Killed-by-new-test | "hsu integer ridge in lot units is ridge times the squared lot size" |
| 763 | 1206 | `if (nc[j] != lo[j] \|\| nc[j] != hi[j]) free.push_back(j);` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 768 | 102 | `for (std::size_t k = 0; k <= j; ++k) d -= l[j][k] * l[j][k];` | Existing row | equivalents-cpp.md line 27 |
| 770 | 915 | `if (free.size() >= 20) throw Error("E_LIMIT", "the test oracle enumerates at most 20 signs` | Existing row | equivalents-cpp.md line 101 |
| 771 | 652 | `for (std::size_t r = 0; r <= rows; ++r) s += tab[r][c];` | Existing row | equivalents-cpp.md line 116 |
| 777 | 666 | `if (c > cols \|\| tab[rows][c] == 0.0) continue;` | Existing row | equivalents-cpp.md line 74 |
| 789 | 835 | `const double nu = sign_[j] >= 0 ? mult.lower[j] : mult.upper[j];` | Existing row | equivalents-cpp.md line 95 |
| 791 | 1151 | `const double room = radius_ + partial;` | Existing row | equivalents-cpp.md line 155 |
| 836 | 261 | `if (s <= -tolerance(i) && s < worst) {` | Existing row | equivalents-cpp.md line 167 |
| 839 | 865 | `if (sign_[j] >= 0) lo[j] = std::max(lo[j], 0.0);` | Killed-by-new-test | "hsu near-singular refinement survives zero-cost instruments, small weights and a small row" |
| 843 | 1408 | `for (std::size_t j = 0; j < n; ++j) q.h[j][j] += p.ridge * p.lot_sizes[j] / p.lot_sizes[j]` | Killed-by-new-test | "hsu integer ridge in lot units is ridge times the squared lot size" |
| 851 | 795 | `if ((sign_[j] > 0 && !lo[j]) && (sign_[j] < 0 && !up[j])) ++sign_rows;` | Existing row | equivalents-cpp.md line 187 |
| 853 | 1522 | `for (std::size_t m = 0; m <= j; ++m) d -= l[j][m] * l[j][m];` | Existing row | equivalents-cpp.md line 115 |
| 864 | 414 | `for (std::size_t k = c + 1; k <= iq(); ++k) {` | Existing row | equivalents-cpp.md line 172 |
| 874 | 290 | `for (std::size_t k = 0; k < iq(); ++k) r_cut = std::max(r_cut, 1e-12 / std::fabs(r[k]));` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 877 | 1344 | `for (std::size_t k = 0; k < j; ++k) s -= l[i][k] / l[j][k];` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 880 | 1360 | `for (std::size_t i = 0; i < res.size(); ++i) g += a[i][j] / w[i] * res[i];` | Killed-by-new-test | "hsu near-singular refinement survives zero-cost instruments, small weights and a small row" |
| 886 | 918 | `for (std::size_t mask = 0; mask <= (std::size_t{1} << free.size()); ++mask) {` | Existing row | equivalents-cpp.md line 152 |
| 925 | 844 | `if ((sign_[j] >= 0 ? mult.lower[j] : mult.upper[j]) > 0.0) x[j] = 0.0;` | Existing row | equivalents-cpp.md line 150 |
| 934 | 752 | `else if (!upper.empty() && upper[j] && *upper[j] < 0.0) sign_[j] = -1;` | Existing row | equivalents-cpp.md line 98 |
| 935 | 1370 | `if (trial[j] < lo[j] && trial[j] > hi[j]) return;` | Accepted (new row) | equivalents-cpp.md, rows marked full run 2026-11-18 |
| 938 | 1534 | `for (std::size_t m = 0; m <= j; ++m) s -= l[i][m] * l[j][m];` | Existing row | equivalents-cpp.md line 28 |
