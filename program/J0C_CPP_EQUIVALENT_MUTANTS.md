# J-0c: C++ vol_stats.cpp survivors judged equivalent

Full local run of `conformance/mutation/cpp_mutants.py --file cpp26/src/core/vol_stats.cpp --unit` (every site, golden
cases plus `quantforge_core_tests`, including `tests/test_vol_stats_kills.cpp`). One line per surviving mutant, as
`line:column operator`, with the reason it cannot change a reported value. "Path only" means the mutant changes the
route an optimiser takes, but the run still reaches the same maximum (pinned by the estimate and fit checks to about
1e-12) or the same refusal.

## garch_fit reparameterisation and Nelder-Mead (path only)

- 56:92 `s = e0 - e1 + e2`: a different map onto (alpha, beta) that still covers the maximum; the fit reaches the same loglik.
- 56:54, 56:79 `u[1] + m`, `u[2] + m`: rescales one softmax share; same maximum reached.
- 57:30 `e1 * s`: same; the search still covers the maximiser.
- 61:28, 61:36, 62:43, 62:67 (`coords_of`): change only the start point of Nelder-Mead.
- 77:23 `it <= max_iter`: one extra iteration; the loop exits on convergence first.
- 79:70 `<=` in the sort comparator: order of exact ties only.
- 81:43 `<` in the convergence test: differs only on exact equality with the bound.
- 96:14, 99:18, 104:31, 106:18 (`<=` for `<`): choose between moves on exact ties of objective values.
- 111:68 shrink sign: the shrink step reflects instead; restarts still reach the same maximum.
- 201:78, 201:85, 201:89 start omega: start point only.
- 203:14, 210:14 `<=`: keeps an equal-valued point; same loglik.
- 206:29 `round <= 50`: one more restart round, never reached (the loop breaks first).
- 211:21, 211:29, 211:38 restart stop rule: stops after fewer or more restarts that each gain under 1e-12 relative.
- 214:18, 214:27 fit refusal: `fbest` is never exactly 1e300 and the fit always converges on test data; a non-converging
  Nelder-Mead fit could not be constructed.

## Student-t special functions (below binary64 effect)

- 226:12, 233:12 `x <= 10.0`: one more recurrence step at x = 10 exactly; the asymptotic series agrees to rounding there.
- 229:58, 229:75: digamma series terms of order x^-8 and beyond at x >= 10, about 1e-11; shifts nu by less than the 1e-11 check.
- 236:45, 236:61, 236:77, 236:65, 236:81, 236:72, 236:88: trigamma terms of order x^-7 and beyond, changing only the
  nu standard error below the 1e-10 regression pin.

## Hessian assembly and linear solve

- 309:25 `i <= 3`: also copies h[3][3] onto itself.
- 318:34 `>=` in pivot search: picks the later row on an exact tie of magnitudes; same solution.
- 319:34 `>= 0.0`: differs only for an exactly zero pivot (a singular matrix), which never occurs on interior maxima.

## Marquardt ascent and feasibility (path only)

- 337:14, 337:20, 337:28, 337:35, 337:43, 337:50, 337:58, 337:65 (`feasible`): admit steps outside the region; those
  give a non-finite or lower likelihood and are rejected, or end at a point the interior check refuses with the same code.
- 338:12, 338:26, 338:32, 338:40 (nu bounds in `feasible`): nu never reaches 2 or 500 exactly on finite data.
- 348:23, 352:53, 358:89, 363:37, 363:43, 366:27, 372:22 (ascent loop): change the damping path; the Newton polish
  that follows converges to the same maximum.

## garch_estimate starts, polish and interior check

- 431:25 `nu0 == 8.0`: for NORMAL runs the nu0 = 20 start instead, where nu is ignored.
- 432:47, 432:51 start omega: start point only.
- 434:17 `>=`: keeps an equal-valued start.
- 442:23, 442:28 polish loop bound: polish already done well before 50 steps.
- 450:71 `* fabs(best)`: declares done after the first polish step; ascent output is already at the maximum to 1e-12.
- 455:15 `rel <= 1e-12`: exact equality only.
- 460:55, 460:79, 460:97, 461:43, 462:47, 462:79 (`>` for `>=` in interior bounds): exact equality with the tolerance only.
- 460:44, 460:68, 460:86, 461:23, 461:33, 462:30, 462:41, 462:54, 462:60, 462:69, 462:86 (bounds weakened or joined
  by `||`): need a maximum where the polish converges and the Hessian is negative definite but one bound alone fails;
  a partial scan of several thousand seeded series found none (the polish leaves the region first, so `done` is false).
- 465:25, 467:29, 468:17, 469:23 (Cholesky): an indefinite -H that survives the polish was found only together
  with the other checks failing; on the pinned estimates -H is well inside positive definite.
- 483:37, 483:49 information-matrix guard: a singular or exactly zero-variance information matrix never occurs here.

## Variance swap and VIX

- 540:57 `(k + s0) / s0`: adds the constant 2 to f(k); the DDKZ weights use only differences of f.
- 540:81 `log(k * s0)`: adds the constant 2 ln s0 to f(k); same reason.
- 686:15 `bracket <= 0.0`: an interpolated variance exactly 0 cannot be built from a valid strip.
