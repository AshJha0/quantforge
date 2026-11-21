# Performance standards

Every benchmark records CPU, memory, OS, compiler/runtime, build flags, commit, dataset size, warm-up, repetitions and measurement method.

Report throughput and latency distributions, including p50, p95, p99 and p99.9 where sample sizes support them. Include memory footprint and allocation behaviour.

Do not compare languages using different algorithms, inputs, precision, warm-up or correctness criteria. Separate cold-start from steady-state results. Benchmark end-to-end workloads as well as isolated kernels.

A performance regression threshold must be justified by baseline variance. Never trade correctness or risk controls for a headline latency number.

Long-run behaviour (stage K, K-6). A soak judges memory at an idle point, after a warm-up, by a slope and a range fixed before the run (`specifications/12-platform/soak-eod-capacity.md`, KR-218). State the smallest per-request leak the slope bound can see at the throughput measured: the bound is per hour, a leak is per request, so a rule written for thousands of requests a second is blind at tens (inferred; the 2026-11-20 Python planted leak was missed for this reason, a recorded miss). Every figure names its host: "local laptop, not the acceptance machine" or "GitHub Actions runner (shared, unpinned)".
