//! G-9 performance acceptance for the Q3b ladder: median of 21 timed runs after 5 warm-ups of
//! (a) one Bermudan price and (b) price plus full ladder by reverse mode, same thread, on the
//! inputs of `aadladder_g-0001`. Prints the ratio and exits non-zero when it exceeds 5.
use std::hint::black_box;
use std::time::Instant;

use quantforge_core::bermudan_aad::bermudan_ladder;
use quantforge_core::shortrate::{FdGrid, HwCurve, SwapLeg, bermudan_swaption};

fn median(mut f: impl FnMut()) -> f64 {
    for _ in 0..5 {
        f();
    }
    let mut t: Vec<f64> = (0..21)
        .map(|_| {
            let s = Instant::now();
            f();
            s.elapsed().as_secs_f64()
        })
        .collect();
    t.sort_by(f64::total_cmp);
    t[10]
}

fn main() {
    let times = [
        0.498_630_136_986_301_4,
        1.0,
        2.0,
        3.0,
        5.002_739_726_027_397,
        7.005_479_452_054_795,
        10.005_479_452_054_795,
        15.010_958_904_109_59,
        20.013_698_630_136_986,
        30.019_178_082_191_782,
    ];
    let dfs = [
        0.98085, 0.9619, 0.9254, 0.8906, 0.8242, 0.762, 0.6787, 0.561, 0.467, 0.332,
    ];
    let curve = HwCurve::new(&times, &dfs).expect("curve");
    let pay = [2.0, 3.0, 4.0, 5.0, 6.0];
    let swap = SwapLeg {
        start: 1.0,
        pay: &pay,
        fixed_rate: 0.039_462,
        payer: true,
        notional: 1e6,
    };
    let ex = [1.0, 2.0, 3.0, 4.0, 5.0];
    let grid = FdGrid {
        nx: 101,
        steps_per_year: 50,
        width: 6.0,
    };
    let a = median(|| {
        black_box(bermudan_swaption(&curve, 0.05, 0.01, &swap, &ex, grid).expect("price"));
    });
    let b = median(|| {
        black_box(bermudan_ladder(&curve, 0.05, 0.01, &swap, &ex, grid).expect("ladder"));
    });
    let ratio = b / a;
    println!("G-9 ladder cost ratio: {ratio:.3} (price {a:.6e} s, ladder {b:.6e} s; pass <= 5)");
    if ratio > 5.0 {
        std::process::exit(1);
    }
}
