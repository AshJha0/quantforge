//! Q5a: limit-case and convergence-order checks for the stage E numerical methods that have
//! no outside source (plan section 12.1). The same checks run in all four languages.
use quantforge_core::exotics::{FdGrid, Vanilla, american_fd, crr, gbs};
use quantforge_core::heston::{Grid, Heston, Market, slv_leverage};
use quantforge_core::pde::{PdeInputs, bs_european};
use quantforge_core::surface_e::Slice;
use quantforge_core::svi::Svi;

fn order(e: &[f64]) -> Vec<f64> {
    e.windows(2).map(|w| (w[0] / w[1]).abs().log2()).collect()
}

fn put(rate: f64) -> Vanilla {
    Vanilla {
        spot: 100.0,
        strike: 100.0,
        expiry_years: 1.0,
        rate,
        dividend_yield: 0.0,
        vol: 0.2,
        call: false,
    }
}

fn fd(x: &Vanilla, american: bool, nx: i64, nt: i64) -> f64 {
    american_fd(x, american, &FdGrid { nx, nt, width: 5.0 })
        .unwrap()
        .price
}

/// Largest |L - 1| within 0.3 of ln(spot), for a flat 20% surface and a Heston model with
/// v0 = theta = 0.04 and vanishing vol of vol: SLV then reduces to Heston with L = 1.
fn slv_gap(nx: i64, nv: i64, nt: i64) -> f64 {
    let h = Heston {
        v0: 0.04,
        kappa: 2.0,
        theta: 0.04,
        xi: 0.01,
        rho: -0.7,
    };
    let m = Market {
        spot: 100.0,
        expiry_years: 1.0,
        rate: 0.0,
        dividend_yield: 0.0,
        call: true,
    };
    let flat = [Slice {
        expiry_years: 1.0,
        svi: Svi {
            a: 0.04,
            b: 0.0,
            rho: 0.0,
            m: 0.0,
            sigma: 0.1,
        },
    }];
    let x0 = 100f64.ln();
    let g = Grid {
        nx,
        nv,
        nt,
        x_min: x0 - 1.0,
        x_max: x0 + 1.0,
        v_max: 0.25,
    };
    let r = slv_leverage(&m, &h, &flat, &g).unwrap();
    assert!((r.mass - 1.0).abs() < 1e-3, "{}", r.mass);
    r.x.iter()
        .zip(&r.leverage)
        .filter(|(x, _)| (**x - x0).abs() < 0.3)
        .map(|(_, l)| (l - 1.0).abs())
        .fold(0.0, f64::max)
}

#[test]
fn slv_heston_limit_leverage_one_within_discretisation_error() {
    let coarse = slv_gap(41, 20, 20);
    let fine = slv_gap(81, 40, 40);
    assert!(coarse < 0.07, "{coarse}");
    // The gap is discretisation error: it must shrink (about first order) on refinement.
    assert!(fine < 0.6 * coarse, "{coarse} {fine}");
}

#[test]
fn fd_american_put_matches_fine_tree() {
    let x = put(0.05);
    let tree = crr(&x, 1000).unwrap().american;
    let fd_price = fd(&x, true, 401, 1600);
    // Backward Euler error at this grid is about 2e-3; the tree's about 5e-4.
    assert!((fd_price - tree).abs() < 5e-3, "{fd_price} {tree}");
}

#[test]
fn fd_american_put_zero_rate_is_european() {
    let x = put(0.0);
    let am = fd(&x, true, 401, 400);
    let eu = fd(&x, false, 401, 400);
    assert!((am - eu).abs() < 1e-12, "{am} {eu}");
    let bs = gbs(false, 100.0, 100.0, 1.0, 0.0, 0.0, 0.2);
    assert!((am - bs).abs() < 5e-3, "{am} {bs}");
}

#[test]
fn crank_nicolson_second_order() {
    let exact = gbs(true, 100.0, 105.0, 1.0, 0.03, 0.02, 0.2);
    let errs: Vec<f64> = [100i64, 200, 400]
        .iter()
        .map(|&j| {
            let p = PdeInputs {
                call: true,
                spot: 100.0,
                strike: 105.0,
                r: 0.03,
                q: 0.01,
                sigma: 0.2,
                t: 1.0,
                space_steps: j,
                time_steps: j / 2,
                width: 6.0,
                rannacher_steps: 2,
            };
            bs_european(&p).unwrap().price - exact
        })
        .collect();
    for p in order(&errs) {
        assert!((1.8..=2.2).contains(&p), "{p}");
    }
}

#[test]
fn fd_reference_scheme_orders() {
    let x = put(0.05);
    let exact = gbs(false, 100.0, 100.0, 1.0, 0.05, 0.05, 0.2);
    // Space: halve dx and quarter dt, so the O(dt) term keeps pace with O(dx^2).
    let space: Vec<f64> = [(51i64, 25i64), (101, 100), (201, 400)]
        .iter()
        .map(|&(nx, nt)| fd(&x, false, nx, nt) - exact)
        .collect();
    for p in order(&space) {
        assert!((1.8..=2.2).contains(&p), "space {p}");
    }
    // Time: Richardson on successive differences at a fixed fine grid.
    let f: Vec<f64> = [50i64, 100, 200, 400]
        .iter()
        .map(|&nt| fd(&x, false, 401, nt))
        .collect();
    let d: Vec<f64> = f.windows(2).map(|w| w[0] - w[1]).collect();
    for p in order(&d) {
        assert!((0.8..=1.2).contains(&p), "time {p}");
    }
}

#[test]
fn crr_first_order() {
    let x = put(0.05);
    let exact = gbs(false, 100.0, 100.0, 1.0, 0.05, 0.05, 0.2);
    let errs: Vec<f64> = [100i64, 200, 400]
        .iter()
        .map(|&n| crr(&x, n).unwrap().european - exact)
        .collect();
    for p in order(&errs) {
        assert!((0.8..=1.2).contains(&p), "{p}");
    }
}
