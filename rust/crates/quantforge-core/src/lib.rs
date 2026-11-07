//! QuantForge stage A: financial mathematics and shared foundations.
//! Written from `specifications/01-core/`. No third-party code.
#![allow(
    clippy::excessive_precision,
    clippy::needless_range_loop,
    clippy::too_many_arguments,
    clippy::manual_range_contains
)]

pub mod black;
pub mod calendar;
pub mod calib;
pub mod compounding;
pub mod conventions;
pub mod cos;
pub mod curve;
pub mod data;
pub mod dates;
pub mod daycount;
pub mod equity;
pub mod error;
pub mod fx;
pub mod hedge;
pub mod integrate;
pub mod interp;
pub mod json;
pub mod linalg;
pub mod mc;
pub mod ois;
pub mod pde;
pub mod projection;
pub mod risk;
pub mod rng;
pub mod root;
pub mod schedule;
pub mod sha256;
pub mod snapshot;
pub mod sobol;
pub mod stats;
pub mod store;
pub mod time;
pub mod ts;
pub mod units;
