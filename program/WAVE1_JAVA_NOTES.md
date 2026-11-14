# Stage J wave 1, Java lane notes

Spec doubts found while building the Java implementation (`java25/.../research/Research.java`, `cli/OpsResearch.java`). No golden is affected; all 99 pass.

1. Limits above the general array limit. J-5 (bars 1,000,000), J-9 (observations 1,000,000) and J-15 (cells 10,000,000) are larger than the CLI's general array limit of 100,000 elements (`In.MAX_ARRAY`, raised on any input array). In Java a 100,001-bar backtest is `E_LIMIT` today, not a valid run. Should the page limits override the general limit for these operations? Viterbi (J-12, 100,000 steps) agrees with it.
2. PBO under `SHARPE`: J-17 checks each block's own standard deviation. A train or test sample made of several blocks cannot then have zero standard deviation, so no further check is needed. Noted so other languages check per block too, not per combined sample.
3. `research.stats.power`: the spec gives no error code for `alpha` or `power` outside `(0, 1)`. Java uses `E_DOMAIN`, as for `alpha >= power` (`rstats_j-0022`).
4. Viterbi with `T = 0` (an empty `emission` or `observations`) is `E_INPUT` in Java (shape wrong); the spec does not list it.
