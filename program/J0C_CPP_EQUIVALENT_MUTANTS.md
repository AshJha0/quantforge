# J-0c: C++ vol_stats.cpp survivors judged equivalent

Local run over every one of the 533 sites the operator set of `conformance/mutation/cpp_mutants.py` finds in
`cpp26/src/core/vol_stats.cpp` (3 do not build), judged by the vol_stats unit tests (including
`tests/test_vol_stats_kills.cpp`) and the vol golden suites; a lower bound on the `--unit` run, which uses every
suite and every unit test. Result: 443 killed, 87 survived (83.6 %, Wilson 95 % lower bound 80.2 %). One line per surviving mutant, as
`line:column operator`, with the reason it cannot change a reported value. "Path only" means the mutant changes the
route an optimiser takes, but the run still reaches the same maximum (pinned by the estimate and fit checks to about
1e-12) or the same refusal.

## Survivors

- 56:92 `-`: params_of: another map onto (alpha, beta) that still covers the maximiser; garch_fit reaches the same loglik (pinned to 1e-12).
- 56:54 `+`: params_of: another map onto (alpha, beta) that still covers the maximiser; garch_fit reaches the same loglik (pinned to 1e-12).
- 56:79 `+`: params_of: another map onto (alpha, beta) that still covers the maximiser; garch_fit reaches the same loglik (pinned to 1e-12).
- 57:30 `*`: params_of: another map onto (alpha, beta) that still covers the maximiser; garch_fit reaches the same loglik (pinned to 1e-12).
- 61:28 `+`: coords_of: changes only the Nelder-Mead start point.
- 61:36 `+`: coords_of: changes only the Nelder-Mead start point.
- 62:43 `*`: coords_of: changes only the Nelder-Mead start point.
- 62:67 `*`: coords_of: changes only the Nelder-Mead start point.
- 77:23 `<=`: Nelder-Mead path only (exact ties, one extra iteration or a different move); the restarts reach the same maximum.
- 79:70 `<=`: Nelder-Mead path only (exact ties, one extra iteration or a different move); the restarts reach the same maximum.
- 81:43 `<`: Nelder-Mead path only (exact ties, one extra iteration or a different move); the restarts reach the same maximum.
- 96:14 `<=`: Nelder-Mead path only (exact ties, one extra iteration or a different move); the restarts reach the same maximum.
- 99:18 `<=`: Nelder-Mead path only (exact ties, one extra iteration or a different move); the restarts reach the same maximum.
- 104:31 `<=`: Nelder-Mead path only (exact ties, one extra iteration or a different move); the restarts reach the same maximum.
- 106:18 `<=`: Nelder-Mead path only (exact ties, one extra iteration or a different move); the restarts reach the same maximum.
- 111:68 `-`: Nelder-Mead path only (exact ties, one extra iteration or a different move); the restarts reach the same maximum.
- 201:85 `+`: garch_fit start, restart rule or refusal: path only, or a branch (fbest exactly 1e300, a non-converging fit) not reachable on finite data.
- 201:89 `+`: garch_fit start, restart rule or refusal: path only, or a branch (fbest exactly 1e300, a non-converging fit) not reachable on finite data.
- 201:78 `/`: garch_fit start, restart rule or refusal: path only, or a branch (fbest exactly 1e300, a non-converging fit) not reachable on finite data.
- 203:14 `<=`: garch_fit start, restart rule or refusal: path only, or a branch (fbest exactly 1e300, a non-converging fit) not reachable on finite data.
- 206:29 `<=`: garch_fit start, restart rule or refusal: path only, or a branch (fbest exactly 1e300, a non-converging fit) not reachable on finite data.
- 210:14 `<=`: garch_fit start, restart rule or refusal: path only, or a branch (fbest exactly 1e300, a non-converging fit) not reachable on finite data.
- 211:38 `/`: garch_fit start, restart rule or refusal: path only, or a branch (fbest exactly 1e300, a non-converging fit) not reachable on finite data.
- 211:29 `<`: garch_fit start, restart rule or refusal: path only, or a branch (fbest exactly 1e300, a non-converging fit) not reachable on finite data.
- 211:21 `||`: garch_fit start, restart rule or refusal: path only, or a branch (fbest exactly 1e300, a non-converging fit) not reachable on finite data.
- 214:27 `>`: garch_fit start, restart rule or refusal: path only, or a branch (fbest exactly 1e300, a non-converging fit) not reachable on finite data.
- 214:18 `&&`: garch_fit start, restart rule or refusal: path only, or a branch (fbest exactly 1e300, a non-converging fit) not reachable on finite data.
- 226:12 `<=`: digamma/trigamma recurrence edge or highest series term: changes values below binary64 effect on the outputs.
- 233:12 `<=`: digamma/trigamma recurrence edge or highest series term: changes values below binary64 effect on the outputs.
- 236:77 `+`: digamma/trigamma recurrence edge or highest series term: changes values below binary64 effect on the outputs.
- 309:25 `<=`: copies h[3][3] onto itself.
- 318:34 `>=`: linear solve: exact pivot ties or an exactly zero pivot only.
- 319:34 `>=`: linear solve: exact pivot ties or an exactly zero pivot only.
- 337:58 `-`: feasible(): admits steps that are rejected later (non-finite or lower likelihood) or end in the same refusal; nu never hits 2 or 500 exactly.
- 337:65 `<=`: feasible(): admits steps that are rejected later (non-finite or lower likelihood) or end in the same refusal; nu never hits 2 or 500 exactly.
- 337:14 `>=`: feasible(): admits steps that are rejected later (non-finite or lower likelihood) or end in the same refusal; nu never hits 2 or 500 exactly.
- 337:28 `>`: feasible(): admits steps that are rejected later (non-finite or lower likelihood) or end in the same refusal; nu never hits 2 or 500 exactly.
- 337:43 `>`: feasible(): admits steps that are rejected later (non-finite or lower likelihood) or end in the same refusal; nu never hits 2 or 500 exactly.
- 337:20 `||`: feasible(): admits steps that are rejected later (non-finite or lower likelihood) or end in the same refusal; nu never hits 2 or 500 exactly.
- 337:35 `||`: feasible(): admits steps that are rejected later (non-finite or lower likelihood) or end in the same refusal; nu never hits 2 or 500 exactly.
- 337:50 `||`: feasible(): admits steps that are rejected later (non-finite or lower likelihood) or end in the same refusal; nu never hits 2 or 500 exactly.
- 338:40 `<`: feasible(): admits steps that are rejected later (non-finite or lower likelihood) or end in the same refusal; nu never hits 2 or 500 exactly.
- 338:26 `>=`: feasible(): admits steps that are rejected later (non-finite or lower likelihood) or end in the same refusal; nu never hits 2 or 500 exactly.
- 338:12 `!=`: feasible(): admits steps that are rejected later (non-finite or lower likelihood) or end in the same refusal; nu never hits 2 or 500 exactly.
- 338:32 `||`: feasible(): admits steps that are rejected later (non-finite or lower likelihood) or end in the same refusal; nu never hits 2 or 500 exactly.
- 348:23 `<=`: Marquardt ascent path only; the Newton polish then reaches the same maximum.
- 352:53 `/`: Marquardt ascent path only; the Newton polish then reaches the same maximum.
- 358:89 `*`: Marquardt ascent path only; the Newton polish then reaches the same maximum.
- 363:43 `>`: Marquardt ascent path only; the Newton polish then reaches the same maximum.
- 363:37 `||`: Marquardt ascent path only; the Newton polish then reaches the same maximum.
- 366:27 `<=`: Marquardt ascent path only; the Newton polish then reaches the same maximum.
- 372:22 `>=`: Marquardt ascent path only; the Newton polish then reaches the same maximum.
- 431:25 `==`: estimate starts: start point only (NORMAL ignores nu0).
- 432:47 `+`: estimate starts: start point only (NORMAL ignores nu0).
- 432:51 `+`: estimate starts: start point only (NORMAL ignores nu0).
- 434:17 `>=`: estimate starts: start point only (NORMAL ignores nu0).
- 442:23 `<=`: Newton polish loop bound or stop rule: the ascent already sits at the maximum.
- 442:28 `||`: Newton polish loop bound or stop rule: the ascent already sits at the maximum.
- 450:71 `*`: Newton polish loop bound or stop rule: the ascent already sits at the maximum.
- 455:15 `<=`: Newton polish loop bound or stop rule: the ascent already sits at the maximum.
- 460:55 `>`: interior check: exact equality with a tolerance, or a bound that never fails alone once the polish converged (partial seeded scan found none).
- 460:79 `>`: interior check: exact equality with a tolerance, or a bound that never fails alone once the polish converged (partial seeded scan found none).
- 460:97 `>`: interior check: exact equality with a tolerance, or a bound that never fails alone once the polish converged (partial seeded scan found none).
- 460:24 `||`: interior check: exact equality with a tolerance, or a bound that never fails alone once the polish converged (partial seeded scan found none).
- 460:44 `||`: interior check: exact equality with a tolerance, or a bound that never fails alone once the polish converged (partial seeded scan found none).
- 460:68 `||`: interior check: exact equality with a tolerance, or a bound that never fails alone once the polish converged (partial seeded scan found none).
- 460:86 `||`: interior check: exact equality with a tolerance, or a bound that never fails alone once the polish converged (partial seeded scan found none).
- 461:23 `+`: interior check: exact equality with a tolerance, or a bound that never fails alone once the polish converged (partial seeded scan found none).
- 461:33 `+`: interior check: exact equality with a tolerance, or a bound that never fails alone once the polish converged (partial seeded scan found none).
- 461:43 `>`: interior check: exact equality with a tolerance, or a bound that never fails alone once the polish converged (partial seeded scan found none).
- 462:41 `+`: interior check: exact equality with a tolerance, or a bound that never fails alone once the polish converged (partial seeded scan found none).
- 462:69 `+`: interior check: exact equality with a tolerance, or a bound that never fails alone once the polish converged (partial seeded scan found none).
- 462:54 `/`: interior check: exact equality with a tolerance, or a bound that never fails alone once the polish converged (partial seeded scan found none).
- 462:86 `/`: interior check: exact equality with a tolerance, or a bound that never fails alone once the polish converged (partial seeded scan found none).
- 462:47 `>`: interior check: exact equality with a tolerance, or a bound that never fails alone once the polish converged (partial seeded scan found none).
- 462:79 `>`: interior check: exact equality with a tolerance, or a bound that never fails alone once the polish converged (partial seeded scan found none).
- 462:30 `||`: interior check: exact equality with a tolerance, or a bound that never fails alone once the polish converged (partial seeded scan found none).
- 462:60 `||`: interior check: exact equality with a tolerance, or a bound that never fails alone once the polish converged (partial seeded scan found none).
- 465:25 `<`: Cholesky test: no polished maximum with an indefinite -H that passes every other check was found.
- 467:29 `<=`: Cholesky test: no polished maximum with an indefinite -H that passes every other check was found.
- 468:17 `!=`: Cholesky test: no polished maximum with an indefinite -H that passes every other check was found.
- 469:23 `>=`: Cholesky test: no polished maximum with an indefinite -H that passes every other check was found.
- 483:49 `>=`: information-matrix guard: a singular or zero-variance information matrix does not occur at an interior maximum.
- 483:37 `&&`: information-matrix guard: a singular or zero-variance information matrix does not occur at an interior maximum.
- 540:57 `+`: adds a constant to f(k); the DDKZ weights use only differences of f.
- 540:81 `*`: adds a constant to f(k); the DDKZ weights use only differences of f.
- 686:15 `<=`: interpolated variance exactly 0 cannot be built from a valid strip.
