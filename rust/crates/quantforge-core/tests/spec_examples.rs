//! Worked examples and numeric targets quoted in the specifications.
use quantforge_core::calendar::{Bdc, Calendar, easter_sunday};
use quantforge_core::compounding::{Compounding, discount_factor};
use quantforge_core::cos::{CosInputs, Model, european};
use quantforge_core::dates::Date;
use quantforge_core::daycount::{DayCountInputs, year_fraction};
use quantforge_core::integrate::{gauss_kronrod, gauss_legendre};
use quantforge_core::interp::{Method, evaluate, monotone_convex};
use quantforge_core::linalg::{cholesky, eigen_symmetric, solve};
use quantforge_core::mc::{McInputs, Method as Mc, gbm_european};
use quantforge_core::pde::{PdeInputs, bs_european};
use quantforge_core::rng::{Xoshiro, ppnd16, splitmix64};
use quantforge_core::root::{Controls, bisection, brent, newton};
use quantforge_core::sha256::sha256_hex;
use quantforge_core::snapshot::hash;
use quantforge_core::sobol::points;
use quantforge_core::stats::normal_cdf;
use quantforge_core::time::{Zone, parse_instant, parse_local, to_instant, utc_offset};

fn d(s: &str) -> Date {
    Date::parse(s).unwrap()
}

fn yf(c: &str, a: &str, b: &str, i: &DayCountInputs) -> f64 {
    year_fraction(c, d(a), d(b), i).unwrap()
}

fn close(a: f64, b: f64, tol: f64) {
    assert!((a - b).abs() <= tol, "{a} vs {b}");
}

#[test]
fn daycount_examples() {
    let n = DayCountInputs::default();
    close(
        yf("ACT_360", "2024-01-01", "2024-07-01", &n),
        182.0 / 360.0,
        1e-15,
    );
    close(
        yf("ACT_ACT_ISDA", "2003-11-01", "2004-05-01", &n),
        0.497724380567,
        1e-12,
    );
    close(
        yf("ACT_ACT_AFB", "1994-02-10", "1997-06-30", &n),
        3.0 + 140.0 / 365.0,
        1e-14,
    );
    close(
        yf("THIRTY_360_BOND", "2024-01-31", "2024-03-31", &n),
        60.0 / 360.0,
        1e-15,
    );
    close(
        yf("THIRTY_E_PLUS_360", "2024-01-30", "2024-03-31", &n),
        61.0 / 360.0,
        1e-15,
    );
    close(
        yf("THIRTY_E_PLUS_360", "2024-03-31", "2024-03-31", &n),
        0.0,
        0.0,
    );
    let icma = DayCountInputs {
        frequency: Some(2),
        ref_start: Some(d("2003-11-01")),
        ref_end: Some(d("2004-05-01")),
        ..Default::default()
    };
    close(
        yf("ACT_ACT_ICMA", "2003-11-01", "2004-05-01", &icma),
        0.5,
        1e-15,
    );
    let e = year_fraction("ACT_360", d("2024-02-01"), d("2024-01-01"), &n);
    assert_eq!(e.unwrap_err().code, "E_DATE_ORDER");
}

#[test]
fn calendars() {
    assert_eq!(easter_sunday(2024), d("2024-03-31"));
    let g = Calendar::parse("GBLO").unwrap();
    assert!(!g.is_business_day(d("2022-09-19")).unwrap());
    let adjusted = g.adjust(d("2024-03-30"), Bdc::ModifiedFollowing).unwrap();
    assert_eq!(adjusted, d("2024-03-28"));
    let e = g.is_business_day(d("1999-12-31")).unwrap_err();
    assert_eq!(e.code, "E_DATE_RANGE");
}

#[test]
fn compounding_examples() {
    let f = |c| discount_factor(0.05, 2.0, c).unwrap();
    close(f(Compounding::Simple), 1.0 / 1.1, 1e-15);
    close(f(Compounding::Periodic(2.0)), 0.905950645, 1e-9);
    close(f(Compounding::Continuous), 0.904837418, 1e-9);
}

#[test]
fn hashes() {
    assert_eq!(
        sha256_hex(b"abc"),
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    );
    let (c, _) = hash(r#"{"b":1,"a":[true,null,"x\n"]}"#).unwrap();
    assert_eq!(
        c,
        "{\"a\":[true,null,\"x\\u000a\"],\"b\":#3ff0000000000000}"
    );
    assert_eq!(hash("[1]").unwrap_err().code, "E_SCHEMA");
    assert_eq!(hash(r#"{"a":"\ud800"}"#).unwrap_err().code, "E_SCHEMA");
    assert_eq!(hash(r#"{"a":1,"a":2}"#).unwrap_err().code, "E_PARSE");
}

#[test]
fn generators() {
    let mut s = 1234567u64;
    assert_eq!(splitmix64(&mut s), 6457827717110365317);
    let mut g = Xoshiro::from_state([1, 2, 3, 4]);
    assert_eq!(g.next_u64(), 11520);
    assert_eq!(g.next_u64(), 0);
    assert_eq!(g.next_u64(), 1509978240);
    close(ppnd16(0.975), 1.959963984540054, 1e-14);
    assert_eq!(ppnd16(0.5), 0.0);
    let p = points(3, 2, 0).unwrap();
    assert_eq!(p[0], vec![0.5, 0.5, 0.5]);
    assert_eq!(p[1], vec![0.75, 0.25, 0.25]);
    assert_eq!(points(1, 1, 1i64 << 32).unwrap_err().code, "E_INPUT");
}

#[test]
fn roots() {
    let c = Controls {
        x_tol: 1e-12,
        f_tol: 0.0,
        max_iter: 200,
    };
    let f = |x: f64| x.exp() - 2.0;
    let root = 2f64.ln();
    close(bisection(&f, 0.0, 1.0, &c).unwrap().root, root, 1e-10);
    let b = brent(&f, 0.0, 1.0, &c).unwrap();
    close(b.root, root, 1e-10);
    assert!(b.iterations <= 20);
    close(
        newton(&f, &f64::exp, 1.0, None, &c).unwrap().root,
        root,
        1e-10,
    );
    let g = |x: f64| x * x + 1.0;
    let e = bisection(&g, 0.0, 1.0, &c).unwrap_err();
    assert_eq!(e.code, "E_NOT_BRACKETED");
}

#[test]
fn quadrature() {
    let e = std::f64::consts::E - 1.0;
    close(gauss_legendre(&f64::exp, 0.0, 1.0, 16).unwrap(), e, 1e-14);
    let f = |x: f64| 1.0 / x.sqrt();
    close(
        gauss_kronrod(&f, 0.0, 1.0, 1e-10, 500).unwrap().0,
        2.0,
        1e-9,
    );
}

#[test]
fn interpolation_reproduces_knots() {
    let x = [0.0, 1.0, 2.5, 3.0, 4.0];
    let y = [1.0, 2.0, 2.2, 3.5, 3.6];
    for m in [
        Method::CubicNatural,
        Method::CubicNotAKnot,
        Method::CubicClamped {
            start: 0.1,
            end: 0.2,
        },
        Method::Pchip,
        Method::Tension(1.0),
    ] {
        let e = evaluate(m, &x, &y, &x).unwrap();
        for (a, b) in e.values.iter().zip(&y) {
            close(*a, *b, 1e-12);
        }
    }
    let t = [0.5, 1.0, 2.0, 5.0];
    let r = [0.02, 0.025, 0.022, 0.03];
    let (_, z) = monotone_convex(&t, &r, &t, false).unwrap();
    for (a, b) in z.iter().zip(&r) {
        close(*a, *b, 1e-12);
    }
}

#[test]
fn linear_algebra() {
    let a = vec![vec![4.0, 1.0], vec![1.0, 3.0]];
    let x = solve(&a, &[1.0, 2.0]).unwrap();
    close(x[0], 1.0 / 11.0, 1e-14);
    close(cholesky(&a).unwrap()[0][0], 2.0, 1e-15);
    let v = eigen_symmetric(&a).unwrap();
    close(v[0], (7.0 - 5f64.sqrt()) / 2.0, 1e-13);
    let s = vec![vec![1.0, 2.0], vec![2.0, 4.0]];
    assert_eq!(solve(&s, &[1.0, 1.0]).unwrap_err().code, "E_SINGULAR");
}

#[test]
fn normal_cdf_values() {
    close(normal_cdf(0.0), 0.5, 1e-16);
    close(normal_cdf(1.0), 0.8413447460685429, 1e-15);
    assert!(normal_cdf(-37.0) > 0.0);
}

fn bs_call() -> f64 {
    let (s, k, r, q, v, t) = (100.0f64, 100.0f64, 0.05f64, 0.02f64, 0.2f64, 1.0f64);
    let d1 = ((s / k).ln() + (r - q + v * v / 2.0) * t) / (v * t.sqrt());
    let d2 = d1 - v * t.sqrt();
    s * (-q * t).exp() * normal_cdf(d1) - k * (-r * t).exp() * normal_cdf(d2)
}

#[test]
fn pde_target() {
    let p = PdeInputs {
        call: true,
        spot: 100.0,
        strike: 100.0,
        r: 0.05,
        q: 0.02,
        sigma: 0.2,
        t: 1.0,
        space_steps: 400,
        time_steps: 200,
        width: 6.0,
        rannacher_steps: 2,
    };
    close(bs_european(&p).unwrap().price, bs_call(), 1e-3);
}

#[test]
fn monte_carlo_targets() {
    let mut p = McInputs {
        call: true,
        spot: 100.0,
        strike: 100.0,
        r: 0.05,
        q: 0.02,
        sigma: 0.2,
        t: 1.0,
        paths: 100_000,
        steps: 1,
        seed: 42,
        stream: 0,
        method: Mc::Plain,
    };
    let (price, se) = gbm_european(&p).unwrap();
    assert!((price - bs_call()).abs() <= 4.0 * se);
    close(se, 0.045, 0.003);
    p.method = Mc::ControlVariate;
    assert!(gbm_european(&p).unwrap().1 < se);
    p.method = Mc::Antithetic;
    assert!(gbm_european(&p).unwrap().1 < se);
    p.method = Mc::Sobol;
    p.paths = 65536;
    close(gbm_european(&p).unwrap().0, bs_call(), 0.01);
}

#[test]
fn cos_targets() {
    let p = CosInputs {
        call: true,
        spot: 100.0,
        strike: 100.0,
        r: 0.05,
        q: 0.02,
        t: 1.0,
        model: Model::BlackScholes { sigma: 0.2 },
        terms: 256,
        truncation: 10.0,
    };
    close(european(&p).unwrap().0, bs_call(), 1e-10);
}

#[test]
fn time_zones() {
    let i = |s| parse_instant(s).unwrap();
    assert_eq!(
        utc_offset(Zone::London, i("2024-03-31T00:59:59Z")).unwrap(),
        0
    );
    assert_eq!(
        utc_offset(Zone::London, i("2024-03-31T01:00:00Z")).unwrap(),
        3600
    );
    let l = |s| parse_local(s).unwrap();
    let gap = to_instant(Zone::NewYork, l("2024-03-10T02:30:00"), None);
    assert_eq!(gap.unwrap_err().code, "E_NONEXISTENT_LOCAL_TIME");
    let t = l("2024-11-03T01:30:00");
    let e = to_instant(Zone::NewYork, t, None).unwrap_err();
    assert_eq!(e.code, "E_AMBIGUOUS_LOCAL_TIME");
    let earlier = to_instant(Zone::NewYork, t, Some(true)).unwrap();
    assert_eq!(earlier, "2024-11-03T05:30:00Z");
}

#[test]
fn store_chain_and_view() {
    use quantforge_core::json::{Json, parse};
    use quantforge_core::store::Log;
    assert_eq!(Log::read(&[]).unwrap().chain().0, "0".repeat(64));
    let rec = |seq: i64, k: &str, v: &str| {
        let text = format!(
            r#"{{"sequence":{seq},"series_id":"s","event_time":"2024-01-01T00:00:00Z","knowledge_time":"{k}","value":{v}}}"#
        );
        parse(&text).unwrap().0
    };
    let log = vec![
        rec(1, "2024-01-02T00:00:00Z", "1"),
        rec(2, "2024-01-03T00:00:00Z", "2"),
    ];
    let l = Log::read(&log).unwrap();
    l.check().unwrap();
    let as_of = parse_instant("2024-01-02T00:00:00Z").unwrap();
    let row = l.latest(as_of, "s");
    assert_eq!(row.get("value"), Some(&Json::Int(1)));
    let late = vec![log[1].clone(), rec(3, "2024-01-02T00:00:00Z", "3")];
    let e = Log::read(&late).unwrap().check().unwrap_err();
    assert_eq!(e.code, "E_INPUT");
}
