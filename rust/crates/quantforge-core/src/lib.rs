//! QuantForge stage A: financial mathematics and shared foundations.
//! Written from `specifications/01-core/`. No third-party code.
#![allow(
    clippy::excessive_precision,
    clippy::needless_range_loop,
    clippy::too_many_arguments,
    clippy::manual_range_contains
)]

pub mod calendar;
pub mod compounding;
pub mod cos;
pub mod data;
pub mod dates;
pub mod daycount;
pub mod error;
pub mod integrate;
pub mod interp;
pub mod json;
pub mod linalg;
pub mod mc;
pub mod pde;
pub mod rng;
pub mod root;
pub mod sha256;
pub mod snapshot;
pub mod sobol;
pub mod stats;
pub mod time;
pub mod ts;
