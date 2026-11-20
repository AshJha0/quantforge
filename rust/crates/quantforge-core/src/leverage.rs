//! Leverage ratio and large exposures, simplified (plan item K-8i,
//! `leverage-large-exposures.md`).
//!
//! A port of `python/quantforge_core/leverage.py`, rulings KR-50 to KR-53, KR-65 to KR-69 and
//! KR-319 to KR-326 (`specifications/stage-k-rulings-w2.md`). "Simplified" means exactly the spec's
//! Limits: Tier 1, PFE, eligibility of purchased protection, connectedness, exemptions and the
//! standardised CCFs are the caller's. Parameters are read from
//! `specifications/tables/stage_k/lev_leverage.json` and `lex_large_exposures.json`, embedded at
//! build time.
//!
//! Error order (KR-67): `E_SCHEMA` (unlisted enums), structural `E_INPUT`, then `E_DOMAIN`; the
//! finite rule is applied by the CLI before them.
#![allow(clippy::neg_cmp_op_on_partial_ord)] // NaN-safe domain checks, as the spec writes them
use crate::cva::{Table, at, dec, qerr};
use crate::error::Result;
use crate::research_w3::fsum;
use std::collections::{BTreeMap, HashMap, HashSet};
use std::sync::OnceLock;

/// KR-65.
pub const LEVERAGE_LABEL: &str =
    "simplified leverage ratio (LEV30 subset); not a regulatory return";
/// KR-66.
pub const LARGE_EXPOSURES_LABEL: &str =
    "simplified large exposures (LEX subset); not a regulatory return";

const LEV_TEXT: &str = include_str!("../../../../specifications/tables/stage_k/lev_leverage.json");
const LEX_TEXT: &str =
    include_str!("../../../../specifications/tables/stage_k/lex_large_exposures.json");

fn lev() -> &'static Table {
    static T: OnceLock<Table> = OnceLock::new();
    T.get_or_init(|| Table::parse(LEV_TEXT))
}

fn lex() -> &'static Table {
    static T: OnceLock<Table> = OnceLock::new();
    T.get_or_init(|| Table::parse(LEX_TEXT))
}

/// LEV30.49-30.54: the input categories (KR-65) and their table keys.
pub const CCF_CATEGORIES: [(&str, &str); 8] = [
    (
        "DIRECT_CREDIT_SUBSTITUTE",
        "direct_credit_substitutes_and_other_100pct_items",
    ),
    (
        "FORWARD_PURCHASE",
        "direct_credit_substitutes_and_other_100pct_items",
    ),
    (
        "OTHER_CREDIT_SUBSTITUTE",
        "direct_credit_substitutes_and_other_100pct_items",
    ),
    ("NIF_RUF", "nif_ruf"),
    ("TRANSACTION_CONTINGENT", "transaction_related_contingent"),
    ("COMMITMENT", "commitments"),
    ("TRADE_LC", "short_term_trade_lc"),
    ("UNCONDITIONALLY_CANCELLABLE", "unconditionally_cancellable"),
];

/// The CCF category input names.
pub fn ccf_category_names() -> Vec<&'static str> {
    CCF_CATEGORIES.iter().map(|(n, _)| *n).collect()
}

/// KR-53 seniority ranks (a short offsets longs of equal or higher rank).
pub const RANKS: [(&str, u8); 4] = [
    ("COVERED", 4),
    ("SENIOR", 3),
    ("NON_SENIOR", 2),
    ("EQUITY", 1),
];

/// The seniority input names.
pub const SENIORITIES: [&str; 4] = ["COVERED", "SENIOR", "NON_SENIOR", "EQUITY"];

fn rank(seniority: &str) -> u8 {
    RANKS
        .iter()
        .find(|(n, _)| *n == seniority)
        .map_or(0, |(_, r)| *r)
}

fn not_negative(value: f64, field: &str) -> Result<()> {
    if value < 0.0 {
        Err(qerr(
            "E_DOMAIN",
            format!("{field} must not be negative"),
            field,
        ))
    } else {
        Ok(())
    }
}

// --- leverage ratio -------------------------------------------------------------------------------

#[derive(Debug, Clone, PartialEq)]
pub struct DerivativeSet {
    pub v: f64,
    pub pfe: f64,
    pub cvm_received: f64,
    pub cvm_provided: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct WrittenCreditDerivative {
    pub notional: f64,
    pub fair_value: f64,
    pub purchased_offset: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Sft {
    pub gross_assets: f64,
    pub mna: bool,
    pub exposures: Vec<f64>,
    pub collateral: Vec<f64>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct OffBalance {
    pub notional: f64,
    pub ccf_category: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct LeverageResult {
    pub on_balance: f64,
    pub derivatives: f64,
    pub derivative_netting_sets: f64,
    pub written_credit_derivatives: f64,
    pub sfts: f64,
    pub off_balance: f64,
    pub exposure: f64,
    pub ratio: f64,
    pub meets_minimum: bool,
}

fn pmax(a: f64, b: f64) -> f64 {
    // Python max(a, b): a unless b is greater.
    if b > a { b } else { a }
}

fn pmin(a: f64, b: f64) -> f64 {
    // Python min(a, b): a unless b is smaller.
    if b < a { b } else { a }
}

/// LEV30.14-30.16: `alpha (RC + PFE)`, `RC = max(V - CVM received + CVM provided, 0)`.
pub fn derivative_exposure(d: &DerivativeSet) -> f64 {
    lev().num("deriv.alpha") * (pmax(d.v - d.cvm_received + d.cvm_provided, 0.0) + d.pfe)
}

/// LEV30.31 and footnote 384: reduced by a negative fair value only, then by purchased
/// protection, never below 0.
pub fn written_cd_effective_notional(w: &WrittenCreditDerivative) -> f64 {
    pmax(
        w.notional - pmax(0.0, -w.fair_value) - w.purchased_offset,
        0.0,
    )
}

/// LEV30.37: gross assets plus the counterparty measure, netted only under an MNA.
pub fn sft_exposure(s: &Sft) -> f64 {
    let add = if s.mna {
        pmax(
            0.0,
            fsum(s.exposures.iter().copied()) - fsum(s.collateral.iter().copied()),
        )
    } else {
        fsum(
            s.exposures
                .iter()
                .zip(&s.collateral)
                .map(|(e, c)| pmax(0.0, e - c)),
        )
    };
    s.gross_assets + add
}

/// Leverage ratio exposure measure (LEV20.5) and ratio (LEV20.3), simplified (KR-65).
pub fn leverage(
    tier1: f64,
    on_balance: &[f64],
    derivatives: &[DerivativeSet],
    written_credit_derivatives: &[WrittenCreditDerivative],
    sfts: &[Sft],
    off_balance: &[OffBalance],
) -> Result<LeverageResult> {
    for o in off_balance {
        if !CCF_CATEGORIES.iter().any(|(n, _)| *n == o.ccf_category) {
            return Err(qerr(
                "E_SCHEMA",
                format!("ccf_category {} is not listed", o.ccf_category),
                "ccf_category",
            ));
        }
    }
    for s in sfts {
        if s.exposures.len() != s.collateral.len() {
            return Err(qerr(
                "E_INPUT",
                "exposures and collateral differ in length",
                "collateral",
            ));
        }
    }
    if !(tier1 > 0.0) {
        return Err(qerr("E_DOMAIN", "tier1 must be positive", "tier1"));
    }
    for x in on_balance {
        not_negative(*x, "on_balance")?;
    }
    for d in derivatives {
        not_negative(d.cvm_received, "cvm_received")?;
        not_negative(d.cvm_provided, "cvm_provided")?;
        not_negative(d.pfe, "pfe")?;
    }
    for w in written_credit_derivatives {
        not_negative(w.notional, "notional")?;
        not_negative(w.purchased_offset, "purchased_offset")?;
    }
    for s in sfts {
        not_negative(s.gross_assets, "gross_assets")?;
        for e in &s.exposures {
            not_negative(*e, "exposures")?;
        }
        for c in &s.collateral {
            not_negative(*c, "collateral")?;
        }
    }
    for o in off_balance {
        not_negative(o.notional, "notional")?;
    }
    let on = fsum(on_balance.iter().copied());
    let netting_sets = fsum(derivatives.iter().map(derivative_exposure));
    let written = fsum(
        written_credit_derivatives
            .iter()
            .map(written_cd_effective_notional),
    );
    let deriv = netting_sets + written; // KR-320
    let sft = fsum(sfts.iter().map(sft_exposure));
    let ccf = lev().get("ccf");
    let obs = fsum(off_balance.iter().map(|o| {
        let key = CCF_CATEGORIES
            .iter()
            .find(|(n, _)| *n == o.ccf_category)
            .map_or("", |(_, k)| k);
        o.notional * dec(at(ccf, key))
    }));
    let exposure = fsum([on, deriv, sft, obs]); // LEV20.5
    if !(exposure > 0.0) {
        return Err(qerr(
            "E_DOMAIN",
            "the exposure measure is zero: no ratio (KR-321)",
            "on_balance",
        ));
    }
    Ok(LeverageResult {
        on_balance: on,
        derivatives: deriv,
        derivative_netting_sets: netting_sets,
        written_credit_derivatives: written,
        sfts: sft,
        off_balance: obs,
        exposure,
        ratio: tier1 / exposure, // LEV20.3
        meets_minimum: tier1 >= lev().num("min_leverage_ratio") * exposure, // LEV20.7
    })
}

// --- large exposures ------------------------------------------------------------------------------

#[derive(Debug, Clone, PartialEq, Default)]
pub struct LeCounterparty {
    pub id: String,
    pub group: Option<String>,
    pub gsib: bool,
    pub exempt: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct BankingBookExposure {
    pub counterparty: String,
    pub value: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct OffBalanceExposure {
    pub counterparty: String,
    pub notional: f64,
    pub ccf: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Protection {
    pub counterparty: String,
    pub provider: String,
    pub protected: f64,
}

/// A trading book position as KR-51 with a counterparty (KR-66); `maturity_years`,
/// `cash_equity` and `lgd_applies` are read and ignored (LEX30.17-30.18, KR-322).
#[derive(Debug, Clone, PartialEq)]
pub struct TradingPosition {
    pub id: String,
    pub counterparty: String,
    pub seniority: String,
    pub notional: f64,
    pub market_value: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CounterpartyRow {
    pub id: String,
    pub banking_book: f64,
    pub off_balance: f64,
    pub trading_book_net_long: f64,
    pub trading_book_net_short: f64,
    pub protected: f64,
    pub received: f64,
    pub exposure: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct GroupRow {
    pub group: String,
    pub members: Vec<String>,
    pub exposure: f64,
    pub share: f64,
    pub large: bool,
    pub limit: f64,
    pub breach: bool,
    pub exempt: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct LargeExposuresResult {
    pub counterparties: Vec<CounterpartyRow>,
    pub groups: Vec<GroupRow>,
    pub report: Vec<String>,
}

/// KR-53 for one obligor: (rank, signed JTD) pairs to (net long, net short).
///
/// Shorts are taken in descending rank (ties: input order); each consumes the longs of equal or
/// higher rank in ascending rank (ties: input order) until it is used up.
pub fn offset_by_seniority(positions: &[(u8, f64)]) -> (f64, f64) {
    let mut longs: Vec<(u8, f64)> = positions.iter().copied().filter(|p| p.1 > 0.0).collect();
    let mut long_order: Vec<usize> = (0..longs.len()).collect();
    long_order.sort_by_key(|&i| (longs[i].0, i));
    let mut shorts: Vec<(u8, f64)> = positions
        .iter()
        .filter(|p| p.1 < 0.0)
        .map(|&(r, j)| (r, -j))
        .collect();
    shorts.sort_by_key(|s| std::cmp::Reverse(s.0)); // stable: input order on ties
    let mut left_short = Vec::with_capacity(shorts.len());
    for (r, mut amount) in shorts {
        for &i in &long_order {
            if amount <= 0.0 {
                break;
            }
            if longs[i].0 >= r && longs[i].1 > 0.0 {
                let used = pmin(amount, longs[i].1);
                longs[i].1 -= used;
                amount -= used;
            }
        }
        left_short.push(amount);
    }
    (fsum(longs.iter().map(|x| x.1)), -fsum(left_short))
}

/// LEX30.17: gross JTD with LGD 100% is the market value, kept on the side of the position
/// (`notional >= 0` is long, KR-323).
pub fn jtd(p: &TradingPosition) -> f64 {
    if p.notional >= 0.0 {
        pmax(p.market_value, 0.0)
    } else {
        pmin(p.market_value, 0.0)
    }
}

fn le_structure(
    counterparties: &[LeCounterparty],
    refs: &[(&str, &str)],
    crm: &[Protection],
    trading_book: &[TradingPosition],
) -> Result<()> {
    let mut group_of: HashMap<&str, Option<&str>> = HashMap::new();
    for c in counterparties {
        if group_of.contains_key(c.id.as_str()) {
            return Err(qerr(
                "E_INPUT",
                format!(
                    "counterparty {} appears twice (so possibly in two groups)",
                    c.id
                ),
                "id",
            ));
        }
        group_of.insert(&c.id, c.group.as_deref());
    }
    for c in counterparties {
        if let Some(g) = c.group.as_deref()
            && let Some(of) = group_of.get(g)
            && *of != Some(g)
        {
            return Err(qerr(
                "E_INPUT",
                format!("group {g} is also a counterparty outside it (KR-324)"),
                "group",
            ));
        }
    }
    for (field, name) in refs {
        if !group_of.contains_key(name) {
            return Err(qerr(
                "E_INPUT",
                format!("unknown counterparty {name}"),
                field,
            ));
        }
    }
    for p in crm {
        if p.provider == p.counterparty {
            return Err(qerr(
                "E_INPUT",
                "a counterparty cannot protect itself",
                "provider",
            ));
        }
    }
    let mut ids = HashSet::new();
    for t in trading_book {
        if !ids.insert(t.id.as_str()) {
            return Err(qerr(
                "E_INPUT",
                format!("position id {} appears twice", t.id),
                "id",
            ));
        }
    }
    Ok(())
}

/// Exposure per counterparty and per group against the LEX20.1 limit, simplified (KR-66).
#[allow(clippy::too_many_arguments)]
pub fn large_exposures(
    tier1: f64,
    counterparties: &[LeCounterparty],
    banking_book: &[BankingBookExposure],
    off_balance: &[OffBalanceExposure],
    crm: &[Protection],
    trading_book: &[TradingPosition],
    bank_gsib: bool,
) -> Result<LargeExposuresResult> {
    for t in trading_book {
        if !SENIORITIES.contains(&t.seniority.as_str()) {
            return Err(qerr(
                "E_SCHEMA",
                format!("seniority {} is not listed", t.seniority),
                "seniority",
            ));
        }
    }
    let mut refs: Vec<(&str, &str)> = Vec::new();
    refs.extend(
        banking_book
            .iter()
            .map(|b| ("counterparty", b.counterparty.as_str())),
    );
    refs.extend(
        off_balance
            .iter()
            .map(|o| ("counterparty", o.counterparty.as_str())),
    );
    refs.extend(
        crm.iter()
            .map(|p| ("counterparty", p.counterparty.as_str())),
    );
    refs.extend(crm.iter().map(|p| ("provider", p.provider.as_str())));
    refs.extend(
        trading_book
            .iter()
            .map(|t| ("counterparty", t.counterparty.as_str())),
    );
    le_structure(counterparties, &refs, crm, trading_book)?;
    if !(tier1 > 0.0) {
        return Err(qerr("E_DOMAIN", "tier1 must be positive", "tier1"));
    }
    for b in banking_book {
        not_negative(b.value, "value")?;
    }
    for o in off_balance {
        not_negative(o.notional, "notional")?;
        if !(0.0 <= o.ccf && o.ccf <= 1.0) {
            return Err(qerr("E_DOMAIN", "ccf must lie in [0, 1]", "ccf"));
        }
    }
    for p in crm {
        not_negative(p.protected, "protected")?;
    }
    let t = lex();
    let ccf_floor = t.num("exposure.obs_ccf_floor");
    let parts = |items: Vec<(&str, f64)>| -> HashMap<String, f64> {
        let mut by: HashMap<&str, Vec<f64>> = counterparties
            .iter()
            .map(|c| (c.id.as_str(), Vec::new()))
            .collect();
        for (name, x) in items {
            by.entry(name).or_default().push(x);
        }
        by.into_iter()
            .map(|(k, v)| (k.to_string(), fsum(v)))
            .collect()
    };
    let bb = parts(
        banking_book
            .iter()
            .map(|b| (b.counterparty.as_str(), b.value))
            .collect(),
    );
    let obs = parts(
        off_balance
            .iter()
            .map(|o| (o.counterparty.as_str(), o.notional * pmax(o.ccf, ccf_floor)))
            .collect(),
    );
    let protected = parts(
        crm.iter()
            .map(|p| (p.counterparty.as_str(), p.protected))
            .collect(),
    );
    let received = parts(
        crm.iter()
            .map(|p| (p.provider.as_str(), p.protected))
            .collect(),
    );
    let mut positions: HashMap<&str, Vec<(u8, f64)>> = counterparties
        .iter()
        .map(|c| (c.id.as_str(), Vec::new()))
        .collect();
    for p in trading_book {
        positions
            .entry(p.counterparty.as_str())
            .or_default()
            .push((rank(&p.seniority), jtd(p)));
    }
    let get = |m: &HashMap<String, f64>, k: &str| m.get(k).copied().unwrap_or(0.0);
    let mut rows = Vec::with_capacity(counterparties.len());
    let mut exposure: HashMap<&str, f64> = HashMap::new();
    for c in counterparties {
        let id = c.id.as_str();
        let (net_long, net_short) =
            offset_by_seniority(positions.get(id).map_or(&[][..], Vec::as_slice)); // LEX30.22-30.23, 30.30
        let gross = fsum([get(&bb, id), get(&obs, id), net_long]);
        let prot = get(&protected, id);
        if prot > gross {
            return Err(qerr(
                "E_DOMAIN",
                format!("counterparty {id}: protected amount above its exposure"),
                "protected",
            ));
        }
        let rec = get(&received, id);
        let e = fsum([gross, -prot, rec]); // LEX30.13-30.15
        exposure.insert(id, e);
        rows.push(CounterpartyRow {
            id: id.to_string(),
            banking_book: get(&bb, id),
            off_balance: get(&obs, id),
            trading_book_net_long: net_long,
            trading_book_net_short: net_short,
            protected: prot,
            received: rec,
            exposure: e,
        });
    }
    let mut members: BTreeMap<&str, Vec<&LeCounterparty>> = BTreeMap::new();
    for c in counterparties {
        members
            .entry(c.group.as_deref().unwrap_or(&c.id))
            .or_default()
            .push(c);
    }
    let (large_share, limit, limit_gsib) = (
        t.num("large_exposure_threshold"),
        t.num("limit"),
        t.num("limit.gsib_to_gsib"),
    );
    let mut groups = Vec::with_capacity(members.len());
    let mut totals: Vec<(f64, &str, bool)> = Vec::with_capacity(members.len());
    for (name, ms) in &members {
        let ex = |c: &&LeCounterparty| exposure.get(c.id.as_str()).copied().unwrap_or(0.0);
        let total = fsum(ms.iter().map(ex)); // LEX10.9
        let counted = fsum(ms.iter().filter(|c| !c.exempt).map(ex)); // KR-325
        let gsib = bank_gsib && ms.iter().any(|c| c.gsib); // KR-324
        let lim = (if gsib { limit_gsib } else { limit }) * tier1;
        let large = total >= large_share * tier1; // LEX10.8, binary64 (KR-326)
        totals.push((total, name, large));
        groups.push(GroupRow {
            group: (*name).to_string(),
            members: ms.iter().map(|c| c.id.clone()).collect(),
            exposure: total,
            share: total / tier1,
            large,
            limit: lim,
            breach: counted > lim,
            exempt: ms.iter().all(|c| c.exempt),
        });
    }
    // LEX20.4: largest first, ties by name.
    totals.sort_by(|a, b| {
        b.0.partial_cmp(&a.0)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then_with(|| a.1.cmp(b.1))
    });
    let top_n = t.get("report.top_n").as_int().map_or(20, |n| n as usize);
    let report = totals
        .iter()
        .enumerate()
        .filter(|(n, g)| g.2 || *n < top_n)
        .map(|(_, g)| g.1.to_string())
        .collect();
    Ok(LargeExposuresResult {
        counterparties: rows,
        groups,
        report,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn offset_examples() {
        // A senior short offsets the covered long first in ascending rank order: senior, covered.
        let (l, s) = offset_by_seniority(&[(4, 10.0), (3, 5.0), (3, -8.0)]);
        assert_eq!((l, s), (7.0, 0.0));
        // A covered short cannot offset a senior long.
        let (l, s) = offset_by_seniority(&[(3, 5.0), (4, -8.0)]);
        assert_eq!((l, s), (5.0, -8.0));
        assert_eq!(offset_by_seniority(&[]), (0.0, 0.0));
    }

    #[test]
    fn jtd_sides() {
        let p = |n: f64, mv: f64| TradingPosition {
            id: "p".into(),
            counterparty: "A".into(),
            seniority: "SENIOR".into(),
            notional: n,
            market_value: mv,
        };
        assert_eq!(jtd(&p(10.0, 9.0)), 9.0);
        assert_eq!(jtd(&p(10.0, -1.0)), 0.0);
        assert_eq!(jtd(&p(-10.0, -9.0)), -9.0);
        assert_eq!(jtd(&p(-10.0, 1.0)), 0.0);
        assert_eq!(rank("NONE"), 0);
    }
}
