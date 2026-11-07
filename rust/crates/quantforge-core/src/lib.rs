//! QuantForge stage A: financial mathematics and shared foundations.
//! Written from `specifications/01-core/`. No third-party code.
#![allow(
    clippy::excessive_precision,
    clippy::needless_range_loop,
    clippy::too_many_arguments,
    clippy::manual_range_contains
)]

pub mod black;
pub mod bonds;
pub mod calendar;
pub mod calib;
pub mod compounding;
pub mod conventions;
pub mod cos;
pub mod credit;
pub mod curve;
pub mod curve_fits;
pub mod data;
pub mod dates;
pub mod daycount;
pub mod equity;
pub mod equity_d;
pub mod error;
pub mod fx;
pub mod greeks;
pub mod hedge;
pub mod inflation;
pub mod integrate;
pub mod interp;
pub mod json;
pub mod linalg;
pub mod mc;
pub mod ois;
pub mod pde;
pub mod projection;
pub mod rates_d;
pub mod risk;
pub mod rng;
pub mod root;
pub mod sabr;
pub mod schedule;
pub mod sha256;
pub mod smile;
pub mod snapshot;
pub mod sobol;
pub mod stage_d3;
pub mod stats;
pub mod store;
pub mod surface;
pub mod svi;
pub mod time;
pub mod ts;
pub mod units;
pub mod xccy;
