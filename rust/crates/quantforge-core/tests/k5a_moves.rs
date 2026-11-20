//! K-5 acceptance on the shared moves file `datasets/scenarios/k5a_intraday_moves.json` (the same
//! 50-position book and 1,000 moves in every build): `|estimate - full revaluation| <= bound` on
//! every move. Latency-aware analytics on simulated data.

use quantforge_core::json::{Json, parse};
use quantforge_core::stage_k::{self, ZeroPosition};

#[test]
fn k5a_1000_moves_inside_the_bound() {
    let path = concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../../datasets/scenarios/k5a_intraday_moves.json"
    );
    let text = std::fs::read_to_string(path).expect("moves file");
    let (root, _) = parse(&text).expect("moves file parses");
    let f = |j: &Json| j.as_f64().expect("number");
    let book: Vec<ZeroPosition> = root
        .get("book")
        .and_then(Json::as_array)
        .expect("book")
        .iter()
        .map(|p| {
            let p = p.as_array().expect("position");
            ZeroPosition {
                notional: f(&p[0]),
                maturity: f(&p[1]),
                yield_: f(&p[2]),
            }
        })
        .collect();
    let moves = root.get("moves").and_then(Json::as_array).expect("moves");
    assert_eq!((book.len(), moves.len()), (50, 1000));
    let (mut worst, mut violations) = (0.0_f64, 0);
    for m in moves {
        let h = f(m);
        let r = stage_k::delta_gamma_bound(&book, h).expect("valid book");
        let err = (r.estimate_pnl - stage_k::zero_revalue(&book, h)).abs();
        if !(err <= r.bound) {
            violations += 1;
        }
        worst = worst.max(err / r.bound);
    }
    println!(
        "k5a moves: {} moves, {violations} violations, worst |error| / bound = {worst:.6}",
        moves.len()
    );
    assert_eq!(violations, 0);
}
