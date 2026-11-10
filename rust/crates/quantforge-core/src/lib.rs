//! `QuantForge` stage A: financial mathematics and shared foundations.
//! Written from `specifications/01-core/`. No third-party code.
#![allow(
    clippy::excessive_precision,
    clippy::needless_range_loop,
    clippy::too_many_arguments,
    clippy::manual_range_contains
)]

pub mod aad;
pub mod arb_surface;
pub mod black;
pub mod bonds;
pub mod book_risk;
pub mod calendar;
pub mod calib;
pub mod caps;
pub mod commodity;
pub mod compounding;
pub mod conventions;
pub mod corr;
pub mod cos;
pub mod credit;
pub mod credit_options;
pub mod curve;
pub mod curve_fits;
pub mod curve_interp;
pub mod data;
pub mod dates;
pub mod daycount;
pub mod equity;
pub mod equity_carry;
pub mod error;
pub mod exotics;
pub mod funding;
pub mod fx;
pub mod fx_smile;
pub mod garch;
pub mod garch_estimate;
pub mod greeks;
pub mod hedge;
pub mod heston;
pub mod inflation;
pub mod integrate;
pub mod interp;
pub mod joint;
pub mod json;
pub mod linalg;
pub mod mbs;
pub mod mc;
pub mod ois;
pub mod pde;
pub mod projection;
pub mod rates_overnight;
pub mod rates_vol;
pub mod risk;
pub mod risk_curve;
pub mod risk_tools;
pub mod rng;
pub mod root;
pub mod sabr;
pub mod schedule;
pub mod sha256;
pub mod smile;
pub mod snapshot;
pub mod sobol;
pub mod stats;
pub mod store;
pub mod surface;
pub mod svi;
pub mod time;
pub mod ts;
pub mod units;
pub mod varswap;
pub mod vix;
pub mod xccy;
