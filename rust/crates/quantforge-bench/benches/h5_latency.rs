//! H-5 p50/p99 harness (`specifications/10-execution/library-interfaces.md` section 3), Rust
//! entries. Run with `cargo bench -p quantforge-bench --bench h5_latency -- "<machine label>"`;
//! prints one JSON object. Same workloads as `java25/.../bench/H5Latency.java`, including its two
//! marked deviations (B1*: the unjittered 13-quote example; B2*: one 5Y PAY trade). B4 is not run.
//! Thread safety: not safe to share; single-threaded main.
use std::fmt::Write as _;
use std::hint::black_box;
use std::path::Path;
use std::time::Instant;

use quantforge_core::black::{Model, Option_};
use quantforge_core::calendar::parse_tenor;
use quantforge_core::conventions;
use quantforge_core::curve::{Interpolation, SolveMethod};
use quantforge_core::dates::Date;
use quantforge_core::exec_api::{self as api, AcParams, Fill, FillMode, Side};
use quantforge_core::json::{self, Json};
use quantforge_core::ois::{self, OisCurveProblem, OisQuote, OisTrade};

fn rank(sorted: &[f64], q: f64) -> f64 {
    sorted[(q * sorted.len() as f64).ceil() as usize - 1] // nearest rank
}

fn run(id: &str, mut f: impl FnMut() -> f64, n: usize, batch: usize, sink: &mut f64) -> String {
    let (mut p50, mut p99) = (Vec::new(), Vec::new());
    for _ in 0..5 {
        for _ in 0..20_000 {
            *sink += black_box(f());
        }
        let mut t = Vec::with_capacity(n);
        for _ in 0..n {
            let a = Instant::now();
            for _ in 0..batch {
                *sink += black_box(f());
            }
            t.push(a.elapsed().as_nanos() as f64);
        }
        t.sort_by(f64::total_cmp);
        p50.push(rank(&t, 0.50) / batch as f64);
        p99.push(rank(&t, 0.99) / batch as f64);
    }
    p50.sort_by(f64::total_cmp);
    p99.sort_by(f64::total_cmp);
    format!(
        "{{\"id\":\"{id}\",\"p50\":{:.1},\"p99\":{:.1},\"batch\":{batch}}}",
        p50[2], p99[2]
    )
}

fn main() {
    let machine = std::env::args()
        .skip(1)
        .find(|a| !a.starts_with('-'))
        .unwrap_or_else(|| "unlabelled machine, not the acceptance machine".into());
    let mut rng = quantforge_core::rng::Xoshiro::seeded(20_261_118, 0);
    let mut u = || (rng.next_u64() >> 11) as f64 / (1u64 << 53) as f64;
    let profile: Vec<f64> = (0..390).map(|_| 0.5 + u()).collect();
    let ac = AcParams::new(1e6, 5.0, 100, 0.95, 0.0625, 2.5e-6, 2.5e-7).expect("valid");
    let fills: Vec<Fill> = (0..1000)
        .map(|_| Fill::new(1.0 + (u() * 100.0).floor(), 100.0 + u()).expect("valid"))
        .collect();
    let fx: f64 = fills.iter().map(Fill::quantity).sum();

    let path =
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../../../examples/ois_bootstrap_sofr.json");
    let text = std::fs::read_to_string(&path).expect("read example");
    let (doc, _) = json::parse(&text).expect("parse example");
    let i = doc.get("inputs").expect("inputs");
    let s = |k: &str| i.get(k).and_then(Json::as_str).expect(k);
    let c = conventions::overnight(s("convention")).expect("convention");
    let as_of = Date::parse(s("as_of")).expect("as_of");
    let quotes: Vec<OisQuote> = i
        .get("quotes")
        .and_then(Json::as_array)
        .expect("quotes")
        .iter()
        .map(|q| {
            let r = q.get("rate").and_then(Json::as_f64).expect("rate");
            let t = q.get("tenor").and_then(Json::as_str).expect("tenor");
            OisQuote {
                tenor: parse_tenor(t).expect("tenor"),
                bid: r,
                ask: r,
            }
        })
        .collect();
    let problem =
        OisCurveProblem::new(&c, as_of, &quotes, Interpolation::LogLinearDf).expect("problem");
    let curve = problem
        .solve(&problem.mids, SolveMethod::Sequential)
        .expect("solve")
        .curve;
    let trade = OisTrade {
        convention: conventions::overnight("SOFR").expect("SOFR"),
        tenor: (5, 'Y'),
        fixed_rate: 0.035,
        notional: 1_000_000.0,
        pay: true,
    };
    let opt = Option_ {
        model: Model::Black76 {
            forward: 100.0,
            discount: 1.0,
            shift: 0.0,
        },
        call: true,
        strike: 105.0,
        t: 1.0,
    };
    let price = opt.price(0.2).expect("price");

    let mut clock: Vec<f64> = (0..10_000)
        .map(|_| {
            let a = Instant::now();
            a.elapsed().as_nanos() as f64
        })
        .collect();
    clock.sort_by(f64::total_cmp);

    let mut sink = 0.0;
    let rows = [
        run(
            "E1",
            || {
                api::twap(1_000_003.0, 100, FillMode::Units)
                    .expect("ok")
                    .slices()[0]
                    .value()
            },
            100_000,
            1,
            &mut sink,
        ),
        run(
            "E2",
            || {
                api::vwap(1_000_003.0, &profile, FillMode::Units)
                    .expect("ok")
                    .slices()[0]
                    .value()
            },
            100_000,
            1,
            &mut sink,
        ),
        run(
            "E3",
            || api::ac_trajectory(&ac, 1e-6).expect("ok").objective(),
            100_000,
            1,
            &mut sink,
        ),
        run(
            "E4",
            || {
                api::shortfall(Side::Buy, 100.0, 100.2, 100.5, fx, &fills, 0.0, Some(100.4))
                    .expect("ok")
                    .total()
            },
            100_000,
            1,
            &mut sink,
        ),
        run(
            "E5",
            || {
                api::as_quotes(100.0, 3.0, 0.1, 2.0, 0.5, 1.5)
                    .expect("ok")
                    .bid()
            },
            100_000,
            100,
            &mut sink,
        ),
        run(
            "E6",
            || api::impact_sqrt(1e5, 1e7, 0.02, 0.5).expect("ok"),
            100_000,
            100,
            &mut sink,
        ),
        run(
            "B1*",
            || {
                problem
                    .solve(black_box(&problem.mids), SolveMethod::Sequential)
                    .expect("solve")
                    .max_repricing_error
            },
            10_000,
            1,
            &mut sink,
        ),
        run(
            "B2*",
            || ois::pv(&curve, &trade, None).expect("pv").0.pv,
            100_000,
            1,
            &mut sink,
        ),
        run(
            "B3",
            || opt.implied(black_box(price)).expect("implied"),
            100_000,
            1,
            &mut sink,
        ),
    ];
    let mut out = String::new();
    write!(
        out,
        "{{\"machine\":\"{machine}\",\"language\":\"Rust\",\"clock\":\"std::time::Instant\",\"clock_overhead_ns_p50\":{:.1},\"unit\":\"ns per call, median of 5 repeats\",\"rows\":[{}],\"sink\":{}}}",
        clock[5000],
        rows.join(","),
        sink != 0.0
    )
    .expect("write");
    println!("{out}");
}
