//! The operation registry. Each domain module declares its operations once, with
//! `registry!`, which yields both its name table and its dispatcher. The verb table
//! (`operations()`) is generated from the registry, so a name cannot exist without a handler.
mod bond;
mod book;
mod calib;
mod cmdty;
mod core;
mod credit;
mod eq;
mod exotic;
mod fx;
mod hedge;
mod infl;
mod mbs;
mod rates;
mod repo;
mod risk;
mod shortrate;
mod usecase;
mod vol;

use crate::input::Inputs;
use quantforge_core::error::{Result, fail};
use quantforge_core::json::Json;
use std::sync::OnceLock;

pub struct Outcome {
    pub outputs: Json,
    pub diagnostics: Json,
}

// Ops return Result uniformly so the dispatcher can treat them alike.
#[allow(clippy::unnecessary_wraps)]
pub fn plain(outputs: Json) -> Result<Outcome> {
    Ok(Outcome {
        outputs,
        diagnostics: Json::Obj(Vec::new()),
    })
}

/// Declares a domain's operations: `"name" => handler expression`, where the expression may use
/// `op` and `i` and returns `Result<Outcome>` (`?` and `return` work as in a function body).
macro_rules! registry {
    (($op:ident, $i:ident) $($($name:literal)|+ => $body:expr),+ $(,)?) => {
        pub const NAMES: &[&str] = &[$($($name),+),+];

        #[allow(clippy::redundant_closure_call)]
        pub fn dispatch($op: &str, $i: &Inputs) -> Option<Result<Outcome>> {
            let _ = &$i;
            Some(match $op {
                $($($name)|+ => (|| -> Result<Outcome> { $body })(),)+
                _ => return None,
            })
        }
    };
}
pub(crate) use registry;

type Handler = fn(&str, &Inputs) -> Option<Result<Outcome>>;

/// One row per domain: the first segment of its operation names, the names, the handler.
const DOMAINS: &[(&str, &[&str], Handler)] = &[
    ("bond", bond::NAMES, bond::dispatch),
    ("book", book::NAMES, book::dispatch),
    ("calib", calib::NAMES, calib::dispatch),
    ("cmdty", cmdty::NAMES, cmdty::dispatch),
    ("core", core::NAMES, core::dispatch),
    ("credit", credit::NAMES, credit::dispatch),
    ("eq", eq::NAMES, eq::dispatch),
    ("exotic", exotic::NAMES, exotic::dispatch),
    ("fx", fx::NAMES, fx::dispatch),
    ("hedge", hedge::NAMES, hedge::dispatch),
    ("infl", infl::NAMES, infl::dispatch),
    ("mbs", mbs::NAMES, mbs::dispatch),
    ("rates", rates::NAMES, rates::dispatch),
    ("rates", shortrate::NAMES, shortrate::dispatch),
    ("repo", repo::NAMES, repo::dispatch),
    ("risk", risk::NAMES, risk::dispatch),
    ("usecase", usecase::NAMES, usecase::dispatch),
    ("vol", vol::NAMES, vol::dispatch),
];

/// Every operation, sorted: the verb table printed by the bare CLI.
pub fn operations() -> &'static [&'static str] {
    static ALL: OnceLock<Vec<&'static str>> = OnceLock::new();
    ALL.get_or_init(|| {
        let mut v: Vec<&str> = DOMAINS.iter().flat_map(|d| d.1.iter().copied()).collect();
        v.sort_unstable();
        v
    })
}

pub fn dispatch(op: &str, i: &Inputs) -> Result<Outcome> {
    let domain = op.split('.').next().unwrap_or_default();
    DOMAINS
        .iter()
        .filter(|d| d.0 == domain)
        .find_map(|d| (d.2)(op, i))
        .unwrap_or_else(|| {
            fail(
                "E_UNSUPPORTED_OPERATION",
                format!("{op} is not in this build"),
            )
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn registry_is_consistent() {
        let all = operations();
        assert!(all.windows(2).all(|w| w[0] < w[1]), "names are unique");
        for (domain, names, _) in DOMAINS {
            for n in *names {
                assert_eq!(n.split('.').next(), Some(*domain), "{n} is in {domain}");
            }
        }
        assert!(DOMAINS.windows(2).all(|w| w[0].0 < w[1].0));
    }
}
