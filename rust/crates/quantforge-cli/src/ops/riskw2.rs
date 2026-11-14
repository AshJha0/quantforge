//! Stage J wave 2 `risk.*` operations: Euler contributions and the Z2 ES backtest.
use super::{Outcome, plain};
use crate::input::Inputs;
use quantforge_core::error::Result;
use quantforge_core::json::obj;
use quantforge_core::portfolio_opt as po;

super::registry! {
(op, i)
        "risk.contrib.euler" => {
            let (w, s) = (i.reals("weights")?, i.matrix("covariance")?);
            i.gate()?;
            let e = po::euler(&w, &s)?;
            plain(obj([
                ("volatility", e.volatility.into()),
                ("marginal", e.marginal.into()),
                ("contributions", e.contributions.into()),
                ("shares", e.shares.into()),
            ]))
        },
        "risk.backtest.es_z2" => es_z2(i),
}

fn es_z2(i: &Inputs) -> Result<Outcome> {
    let (l, v, e) = (i.reals("losses")?, i.reals("var")?, i.reals("es")?);
    let a = i.f64("alpha")?;
    i.gate()?;
    let (z2, n, ta) = po::es_z2(&l, &v, &e, a)?;
    plain(obj([
        ("z2", z2.into()),
        ("exceptions", n.into()),
        ("expected_exceptions", ta.into()),
    ]))
}
