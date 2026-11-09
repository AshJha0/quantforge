//! In-language microbenchmarks (plan item G2): `bootstrap`, `swap_pv`, `implied_vol`.
//! Writes `benchmarks/micro/out/rust.json` at the repo root after criterion finishes.
//! `QF_BENCH_INJECT_NS` adds a busy-wait to every timed op (used to prove the CI gate fails).
use std::alloc::{GlobalAlloc, Layout, System};
use std::hint::black_box;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, Instant};

use criterion::Criterion;
use quantforge_core::black::{Model, Option_};
use quantforge_core::calendar::parse_tenor;
use quantforge_core::conventions;
use quantforge_core::curve::{Curve, Interpolation, SolveMethod};
use quantforge_core::dates::Date;
use quantforge_core::json::{self, Json};
use quantforge_core::ois::{self, OisCurveProblem, OisQuote, OisTrade};

struct Counting;
static ALLOCS: AtomicU64 = AtomicU64::new(0);

// SAFETY: forwards to System; only adds a counter.
unsafe impl GlobalAlloc for Counting {
    unsafe fn alloc(&self, l: Layout) -> *mut u8 {
        ALLOCS.fetch_add(1, Ordering::Relaxed);
        unsafe { System.alloc(l) }
    }
    unsafe fn dealloc(&self, p: *mut u8, l: Layout) {
        unsafe { System.dealloc(p, l) }
    }
    unsafe fn alloc_zeroed(&self, l: Layout) -> *mut u8 {
        ALLOCS.fetch_add(1, Ordering::Relaxed);
        unsafe { System.alloc_zeroed(l) }
    }
    unsafe fn realloc(&self, p: *mut u8, l: Layout, n: usize) -> *mut u8 {
        ALLOCS.fetch_add(1, Ordering::Relaxed);
        unsafe { System.realloc(p, l, n) }
    }
}

#[global_allocator]
static GLOBAL: Counting = Counting;

const ALLOC_RUNS: u64 = 1000;

fn inject_ns() -> u64 {
    std::env::var("QF_BENCH_INJECT_NS")
        .ok()
        .and_then(|s| s.trim().parse().ok())
        .unwrap_or(0)
}

fn spin(ns: u64) {
    if ns > 0 {
        let t = Instant::now();
        let d = Duration::from_nanos(ns);
        while t.elapsed() < d {
            std::hint::spin_loop();
        }
    }
}

fn repo_root() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..")
}

struct Setup {
    problem: OisCurveProblem,
    method: SolveMethod,
}

fn load_setup() -> Setup {
    let path = repo_root().join("examples/ois_bootstrap_sofr.json");
    let text = std::fs::read_to_string(&path).expect("read example");
    let (doc, _) = json::parse(&text).expect("parse example");
    let i = doc.get("inputs").expect("inputs");
    let s = |k: &str| i.get(k).and_then(Json::as_str).expect(k);
    let c = conventions::overnight(s("convention")).expect("convention");
    let as_of = Date::parse(s("as_of")).expect("as_of");
    let interp = Interpolation::parse(s("interpolation")).expect("interpolation");
    let method = match s("method") {
        "GLOBAL" => SolveMethod::Global,
        _ => SolveMethod::Sequential,
    };
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
    let problem = OisCurveProblem::new(&c, as_of, &quotes, interp).expect("problem");
    Setup { problem, method }
}

fn allocs_per_op(mut f: impl FnMut()) -> f64 {
    f();
    let before = ALLOCS.load(Ordering::Relaxed);
    for _ in 0..ALLOC_RUNS {
        f();
    }
    (ALLOCS.load(Ordering::Relaxed) - before) as f64 / ALLOC_RUNS as f64
}

fn median_ns(id: &str) -> f64 {
    let p = repo_root()
        .join("rust/target/criterion")
        .join(id)
        .join("new/estimates.json");
    let p = std::env::var_os("CARGO_TARGET_DIR").map_or(p, |t| {
        PathBuf::from(t)
            .join("criterion")
            .join(id)
            .join("new/estimates.json")
    });
    let text = std::fs::read_to_string(&p).unwrap_or_else(|e| panic!("{}: {e}", p.display()));
    let (j, _) = json::parse(&text).expect("estimates");
    j.get("median")
        .and_then(|m| m.get("point_estimate"))
        .and_then(Json::as_f64)
        .expect("median.point_estimate")
}

fn main() {
    let inject = inject_ns();
    let setup = load_setup();
    let bootstrap = || {
        let s = setup
            .problem
            .solve(&setup.problem.mids, setup.method)
            .expect("solve");
        spin(inject);
        s
    };
    let curve: Curve = bootstrap().curve;
    let trade = OisTrade {
        convention: conventions::overnight("SOFR").expect("SOFR"),
        tenor: (10, 'Y'),
        fixed_rate: 0.0375,
        notional: 10_000_000.0,
        pay: true,
    };
    let swap_pv = || {
        let v = ois::pv(&curve, &trade, None).expect("pv").0.pv;
        spin(inject);
        v
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
    let implied = || {
        let v = opt.implied(black_box(price)).expect("implied");
        spin(inject);
        v
    };

    let mut c = Criterion::default()
        .sample_size(30)
        .warm_up_time(Duration::from_millis(500))
        .measurement_time(Duration::from_secs(3))
        .configure_from_args();
    c.bench_function("bootstrap", |b| b.iter(|| black_box(bootstrap())));
    c.bench_function("swap_pv", |b| b.iter(|| black_box(swap_pv())));
    c.bench_function("implied_vol", |b| b.iter(|| black_box(implied())));
    c.final_summary();

    let allocs = [
        ("bootstrap", allocs_per_op(|| drop(black_box(bootstrap())))),
        ("swap_pv", allocs_per_op(|| drop(black_box(swap_pv())))),
        ("implied_vol", allocs_per_op(|| drop(black_box(implied())))),
    ];
    let mut out = String::from("{\"lang\":\"rust\",\"benchmarks\":{");
    for (n, (id, a)) in allocs.iter().enumerate() {
        if n > 0 {
            out.push(',');
        }
        let ns = median_ns(id);
        out.push_str(&format!(
            "\"{id}\":{{\"ns_per_op\":{ns},\"allocs_per_op\":{a}}}"
        ));
    }
    out.push_str("}}\n");
    let dir = repo_root().join("benchmarks/micro/out");
    std::fs::create_dir_all(&dir).expect("mkdir");
    std::fs::write(dir.join("rust.json"), &out).expect("write rust.json");
    print!("{out}");
}
