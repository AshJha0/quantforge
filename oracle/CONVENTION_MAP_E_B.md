# Convention map for stage E spec B outside-oracle checks

Plan rule 11.2.5. Rows used by `oracle/python/outside_e_b.py`, from `oracle/python/qf_oracle/convmap_e_b.py`. Base rows are the stage D table (`oracle/CONVENTION_MAP.md`); only the new rows are listed here.

Library: QuantLib 1.44 (Python wheel). Version recorded per case in `oracle/outside_register_e_b.json`.

Review: self-reviewed 2026-11-08. Self-assessment, not an outside review.

| Row | Spec | QuantLib object | Note |
|---|---|---|---|
| `VS.DDKZ_SPOT` | 05-volatility/variance-swaps.md replication: DDKZ weights, reference S* = spot, puts walked down, calls up, one extension strike | `ql.ReplicatingVarianceSwapEngine(proc, dk, calls, puts` | QuantLib's drift term is 2/T (rT - (e^{rT} - 1)); it ignores the dividend yield, so only q = 0 cases are mapped (ruling E-B3) |
| `VS.INSTRUMENT` | 05-volatility/variance-swaps.md pv = N_var D (K_fair - K_var), long | `ql.VarianceSwap(ql.Position.Long, K, N, a, m), ""` |  |
| `PROC.BSM` | 05-volatility/variance-swaps.md flat continuous r and q on ACT/365F; Black vol per listed strike | `ql.BlackScholesMertonProcess(s, q, r, v), ""` |  |
| `CRV.FLAT_CONT_365F` | 05-volatility/variance-swaps.md flat continuously compounded rate, ACT/365F | `ql.YieldTermStructureHandle(ql.FlatForward(a, r, ql.Actual365Fixed(), ql.Continuous)), ""` |  |
| `VOL.STRIKE_TABLE` | 05-volatility/variance-swaps.md vols given at listed strikes only; the engine reads them only there | `ql.BlackVarianceSurface(a, ql.NullCalendar(), dates, ks, m, ql.Actual365Fixed(` | two identical maturity columns so the surface is defined; read only at listed strikes and the maturity |
