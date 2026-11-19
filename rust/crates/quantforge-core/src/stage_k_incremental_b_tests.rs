//! K-4b on the stage B production bootstrap (incremental-update.md, Acceptance, third line; KR-5):
//! on 10,000 quote moves over every sequential stage B instrument set, the incremental path
//! equals a full rebuild to 1e-12 relative and the copied pillars are bit-identical to the cache.
//! The sets and the move plan are those of the Python test (test_stage_k_w1.py); the random part
//! draws from a SplitMix64 stream seeded 20261119.

use crate::calendar::parse_tenor;
use crate::conventions::{Overnight, overnight};
use crate::curve::{Curve, CurveInput, Incremental, Interpolation, SolveMethod, Solved};
use crate::dates::Date;
use crate::error::Result;
use crate::json::{Json, parse};
use crate::ois::{OisCurveProblem, OisQuote};
use crate::projection::{ProjectionQuote, bootstrap, bootstrap_incremental};

const BP: f64 = 1e-4;

#[derive(Clone, Copy, PartialEq, Debug)]
enum Q {
    Ois(OisQuote),
    Term(ProjectionQuote),
}

fn shift(q: Q, d: f64) -> Q {
    match q {
        Q::Ois(o) => Q::Ois(OisQuote {
            tenor: o.tenor,
            bid: o.bid + d,
            ask: o.ask + d,
        }),
        Q::Term(ProjectionQuote::Deposit { months, rate }) => Q::Term(ProjectionQuote::Deposit {
            months,
            rate: rate + d,
        }),
        Q::Term(ProjectionQuote::Fra { start_months, rate }) => Q::Term(ProjectionQuote::Fra {
            start_months,
            rate: rate + d,
        }),
        Q::Term(ProjectionQuote::Swap { months, rate }) => Q::Term(ProjectionQuote::Swap {
            months,
            rate: rate + d,
        }),
    }
}

struct Set {
    id: String,
    ois: Option<Overnight>,
    jumps: Vec<(Date, f64)>,
    discount: Option<Curve>,
    as_of: Date,
    interpolation: Interpolation,
    quotes: Vec<Q>,
}

impl Set {
    fn ois_quotes(q: &[Q]) -> Vec<OisQuote> {
        q.iter()
            .map(|x| match x {
                Q::Ois(o) => *o,
                Q::Term(_) => unreachable!(),
            })
            .collect()
    }

    fn term_quotes(q: &[Q]) -> Vec<ProjectionQuote> {
        q.iter()
            .map(|x| match x {
                Q::Term(t) => *t,
                Q::Ois(_) => unreachable!(),
            })
            .collect()
    }

    fn problem(&self, q: &[Q]) -> Result<OisCurveProblem> {
        let c = self.ois.as_ref().expect("an OIS set");
        OisCurveProblem::with_jumps(
            c,
            self.as_of,
            &Set::ois_quotes(q),
            self.interpolation,
            &self.jumps,
        )
    }

    fn solve(&self, q: &[Q]) -> Result<Solved> {
        match &self.discount {
            None => {
                let p = self.problem(q)?;
                p.solve(&p.mids, SolveMethod::Sequential)
            }
            Some(d) => bootstrap(d, self.as_of, &Set::term_quotes(q), self.interpolation),
        }
    }

    fn incremental(&self, prev: &[Q], factors: &[f64], next: &[Q]) -> Result<Incremental> {
        match &self.discount {
            None => self
                .problem(next)?
                .solve_incremental(&self.problem(prev)?, factors),
            Some(d) => bootstrap_incremental(
                d,
                self.as_of,
                &Set::term_quotes(prev),
                factors,
                &Set::term_quotes(next),
                self.interpolation,
            ),
        }
    }
}

fn factors(s: &Solved) -> Vec<f64> {
    s.logs.iter().map(|l| l.exp()).collect()
}

fn date(j: &Json, k: &str) -> Date {
    Date::parse(j.get(k).and_then(Json::as_str).expect(k)).expect(k)
}

fn num(j: &Json, k: &str) -> f64 {
    j.get(k).and_then(Json::as_f64).expect(k)
}

fn jumps(i: &Json) -> Vec<(Date, f64)> {
    i.get("jumps")
        .and_then(Json::as_array)
        .unwrap_or(&[])
        .iter()
        .map(|j| (date(j, "date"), num(j, "factor")))
        .collect()
}

fn sets() -> Vec<Set> {
    let mut out = Vec::new();
    for (folder, name) in [
        ("stage_b", "ois"),
        ("stage_b", "projection"),
        ("stage_b", "projection_deep"),
        ("stage_d", "ois_d"),
    ] {
        let path = format!(
            "{}/../../../datasets/golden/{folder}/{name}.json",
            env!("CARGO_MANIFEST_DIR")
        );
        let (doc, _) = parse(&std::fs::read_to_string(path).unwrap()).unwrap();
        for c in doc.get("cases").and_then(Json::as_array).unwrap() {
            let i = c.get("inputs").unwrap();
            let op = c.get("operation").and_then(Json::as_str).unwrap();
            let ok = c
                .get("expected")
                .and_then(|e| e.get("status"))
                .and_then(Json::as_str)
                == Some("ok");
            let method = i
                .get("method")
                .and_then(Json::as_str)
                .unwrap_or("SEQUENTIAL");
            let interp = i.get("interpolation").and_then(Json::as_str).unwrap();
            if !op.ends_with(".bootstrap")
                || !ok
                || method != "SEQUENTIAL"
                || !matches!(interp, "LOG_LINEAR_DF" | "LINEAR_ZERO")
                || i.get("tension").is_some()
                || i.get("step_end").is_some()
            {
                continue;
            }
            let id = c.get("case_id").and_then(Json::as_str).unwrap().to_string();
            let as_of = date(i, "as_of");
            let raw = i.get("quotes").and_then(Json::as_array).unwrap();
            if op == "rates.ois.bootstrap" {
                let quotes = raw
                    .iter()
                    .map(|q| {
                        let tenor =
                            parse_tenor(q.get("tenor").and_then(Json::as_str).unwrap()).unwrap();
                        let (bid, ask) = match q.get("rate").and_then(Json::as_f64) {
                            Some(r) => (r, r),
                            None => (num(q, "bid"), num(q, "ask")),
                        };
                        Q::Ois(OisQuote { tenor, bid, ask })
                    })
                    .collect();
                out.push(Set {
                    id,
                    ois: overnight(i.get("convention").and_then(Json::as_str).unwrap()),
                    jumps: jumps(i),
                    discount: None,
                    as_of,
                    interpolation: Interpolation::parse(interp).unwrap(),
                    quotes,
                });
            } else if op == "rates.projection.bootstrap" {
                let d = i.get("discount").unwrap();
                let pillars = d
                    .get("pillars")
                    .and_then(Json::as_array)
                    .unwrap()
                    .iter()
                    .map(|p| (date(p, "date"), num(p, "discount_factor")))
                    .collect();
                let input = CurveInput {
                    as_of: date(d, "as_of"),
                    interpolation: Interpolation::parse(
                        d.get("interpolation").and_then(Json::as_str).unwrap(),
                    )
                    .unwrap(),
                    pillars,
                    jumps: jumps(d),
                };
                let quotes: Vec<Q> = raw
                    .iter()
                    .map(|q| {
                        let rate = num(q, "rate");
                        let m = |k: &str| q.get(k).and_then(Json::as_f64).unwrap() as i64;
                        Q::Term(match q.get("type").and_then(Json::as_str).unwrap() {
                            "DEPOSIT" => ProjectionQuote::Deposit {
                                months: m("months"),
                                rate,
                            },
                            "FRA" => ProjectionQuote::Fra {
                                start_months: m("start_months"),
                                rate,
                            },
                            _ => ProjectionQuote::Swap {
                                months: m("months"),
                                rate,
                            },
                        })
                    })
                    .collect();
                for interpolation in [Interpolation::LogLinearDf, Interpolation::LinearZero] {
                    out.push(Set {
                        id: format!("{id}/{interpolation:?}"),
                        ois: None,
                        jumps: Vec::new(),
                        discount: Some(Curve::new(&input).unwrap()),
                        as_of,
                        interpolation,
                        quotes: quotes.clone(),
                    });
                }
            }
        }
    }
    out
}

/// SplitMix64: a fixed, documented stream so the random part is reproducible without a crate.
struct Rng(u64);

impl Rng {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    fn below(&mut self, n: usize) -> usize {
        (self.next() % n as u64) as usize
    }

    fn unit(&mut self) -> f64 {
        (self.next() >> 11) as f64 / (1u64 << 53) as f64
    }
}

struct Move {
    set: usize,
    kind: String,
    prev: Vec<Q>,
    next: Vec<Q>,
}

fn moves(sets: &[Set], total: usize, seed: u64) -> Vec<Move> {
    let mut out = Vec::new();
    for (s, set) in sets.iter().enumerate() {
        let base = &set.quotes;
        let n = base.len();
        out.push(Move {
            set: s,
            kind: "none".into(),
            prev: base.clone(),
            next: base.clone(),
        });
        for j in 0..n {
            let mut q = base.clone();
            q[j] = shift(base[j], BP);
            let kind = if j == 0 {
                "single_first"
            } else if j == n - 1 {
                "single_last"
            } else {
                "single_middle"
            };
            out.push(Move {
                set: s,
                kind: kind.into(),
                prev: base.clone(),
                next: q,
            });
        }
        let mut both = base.clone();
        both[0] = shift(base[0], -BP);
        both[n - 1] = shift(base[n - 1], -BP);
        out.push(Move {
            set: s,
            kind: "multi_first_and_last".into(),
            prev: base.clone(),
            next: both,
        });
        let all = base.iter().map(|q| shift(*q, 2.0 * BP)).collect();
        out.push(Move {
            set: s,
            kind: "multi_all".into(),
            prev: base.clone(),
            next: all,
        });
    }
    let mut rng = Rng(seed);
    while out.len() < total {
        let s = rng.below(sets.len());
        let base = &sets[s].quotes;
        let n = base.len();
        let prev: Vec<Q> = base
            .iter()
            .map(|q| {
                if rng.next() & 1 == 1 {
                    shift(*q, (rng.unit() * 2.0 - 1.0) * 50.0 * BP)
                } else {
                    *q
                }
            })
            .collect();
        let mut idx: Vec<usize> = (0..n).collect();
        for k in (1..n).rev() {
            idx.swap(k, rng.below(k + 1));
        }
        idx.truncate(1 + rng.below(n));
        idx.sort_unstable();
        let mut next = prev.clone();
        for &k in &idx {
            let size = (0.01 + rng.unit() * 24.99) * BP;
            next[k] = shift(prev[k], if rng.next() & 1 == 1 { size } else { -size });
        }
        let where_ = if idx[0] == 0 {
            "first"
        } else if idx[0] == n - 1 {
            "last"
        } else {
            "middle"
        };
        let kind = format!(
            "{}_{where_}",
            if idx.len() > 1 { "multi" } else { "single" }
        );
        out.push(Move {
            set: s,
            kind,
            prev,
            next,
        });
    }
    out
}

#[test]
fn incremental_equals_rebuild_on_stage_b() {
    let sets = sets();
    assert_eq!(sets.len(), 25, "the 25 sequential stage B instrument sets");
    let plan = moves(&sets, 10_000, 20_261_119);
    assert_eq!(plan.len(), 10_000);
    let (mut worst, mut bit_equal) = (0.0f64, 0usize);
    let mut kinds = std::collections::BTreeMap::new();
    for m in &plan {
        let s = &sets[m.set];
        let cache = factors(&s.solve(&m.prev).unwrap());
        let inc = s.incremental(&m.prev, &cache, &m.next).unwrap();
        let full = s.solve(&m.next).unwrap();
        let (got, want) = (factors(&inc.solved), factors(&full));
        let n = m.next.len();
        let first = (0..n).find(|&k| m.prev[k] != m.next[k]);
        assert_eq!(inc.first_changed_index, first, "{} {}", s.id, m.kind);
        assert_eq!(inc.recomputed, first.map_or(0, |j| n - j));
        let j = first.unwrap_or(n);
        for k in 0..j {
            assert_eq!(
                cache[k].to_bits(),
                got[k].to_bits(),
                "{} copied pillar {k}",
                s.id
            );
        }
        let mut same = inc.solved.max_repricing_error == full.max_repricing_error;
        for k in 0..n {
            let rel = (got[k] - want[k]).abs() / want[k].abs().max(1e-300);
            worst = worst.max(rel);
            assert!(
                rel <= 1e-12,
                "{} {} pillar {k}: {} {}",
                s.id,
                m.kind,
                got[k],
                want[k]
            );
            same &= got[k].to_bits() == want[k].to_bits();
        }
        bit_equal += usize::from(same);
        *kinds.entry(m.kind.clone()).or_insert(0usize) += 1;
    }
    assert!(kinds.contains_key("single_first") && kinds.contains_key("single_last"));
    assert!(kinds.contains_key("multi_first") && kinds.contains_key("multi_all"));
    assert_eq!(bit_equal, plan.len(), "worst relative difference {worst:e}");
}

#[test]
fn incremental_errors_and_tenor_change() {
    let sets = sets();
    let s = sets.iter().find(|s| s.ois.is_some()).unwrap();
    let q = &s.quotes;
    let f = factors(&s.solve(q).unwrap());
    let code = |r: Result<Incremental>| r.unwrap_err().code;
    let mut stale = f.clone();
    let last = stale.len() - 1;
    stale[last] = f64::from_bits(stale[last].to_bits() + 1);
    assert_eq!(code(s.incremental(q, &stale, q)), "E_INPUT");
    assert_eq!(code(s.incremental(q, &f, &q[..q.len() - 1])), "E_INPUT");
    assert_eq!(code(s.incremental(q, &f[..f.len() - 1], q)), "E_INPUT");
    let smooth = Set {
        interpolation: Interpolation::MonotoneConvex,
        ..clone_ois(s)
    };
    assert_eq!(code(smooth.incremental(q, &f, q)), "E_INPUT");
    let none = s.incremental(q, &f, q).unwrap();
    assert_eq!((none.first_changed_index, none.recomputed), (None, 0));
    assert_eq!(factors(&none.solved), f);
    // a changed tenor is a changed instrument: its pillar and every later one are solved again
    let mut longer = q.clone();
    if let Q::Ois(o) = q[last] {
        assert_eq!(o.tenor, (30, 'Y'));
        longer[last] = Q::Ois(OisQuote {
            tenor: (25, 'Y'),
            ..o
        });
    }
    let t = s.incremental(q, &f, &longer).unwrap();
    assert_eq!((t.first_changed_index, t.recomputed), (Some(last), 1));
    let p = sets.iter().find(|s| s.discount.is_some()).unwrap();
    let mut pf = factors(&p.solve(&p.quotes).unwrap());
    pf[0] = 0.5;
    assert_eq!(code(p.incremental(&p.quotes, &pf, &p.quotes)), "E_INPUT");
}

fn clone_ois(s: &Set) -> Set {
    Set {
        id: s.id.clone(),
        ois: s.ois.clone(),
        jumps: s.jumps.clone(),
        discount: None,
        as_of: s.as_of,
        interpolation: s.interpolation,
        quotes: s.quotes.clone(),
    }
}
