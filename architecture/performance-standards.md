# Performance standards

Every benchmark records CPU, memory, OS, compiler/runtime, build flags, commit, dataset size, warm-up, repetitions and measurement method.

Report throughput and latency distributions, including p50, p95, p99 and p99.9 where sample sizes support them. Include memory footprint and allocation behaviour.

Do not compare languages using different algorithms, inputs, precision, warm-up or correctness criteria. Separate cold-start from steady-state results. Benchmark end-to-end workloads as well as isolated kernels.

A performance regression threshold must be justified by baseline variance. Never trade correctness or risk controls for a headline latency number.
