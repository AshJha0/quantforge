//! Stage K wave 2b `risk.*` operations: CVA capital (K-8g, `cva-capital.md`) and the leverage
//! ratio and large exposures, simplified (K-8i, `leverage-large-exposures.md`). A port of
//! `python/quantforge_core/cli/ops_k_w2b.py`. Every input is read first (`E_SCHEMA`, enum values
//! and factor names included); then the gate (the held `E_LIMIT`; `main.rs` applies the finite rule
//! after it); then the core: structural `E_INPUT` over the whole input, then `E_DOMAIN` (KR-67).
use crate::input::Inputs;
use crate::ops::kw1b::choice;
use crate::ops::{Outcome, plain};
use quantforge_core::cva;
use quantforge_core::error::Result;
use quantforge_core::json::{Json, obj};
use quantforge_core::leverage as lev;

crate::ops::registry! {
(op, i)
        "risk.cva.ba" => cva_ba(i),
        "risk.cva.sa" => cva_sa(i),
        "risk.capital.leverage" => leverage(i),
        "risk.capital.large_exposures" => large_exposures(i),
}

fn objects<'a>(i: &Inputs<'a>, k: &str) -> Result<Vec<Inputs<'a>>> {
    i.array(k)?
        .iter()
        .map(|v| match v {
            Json::Obj(_) => Ok(Inputs::new(v)),
            _ => i.fail(k, "expected objects"),
        })
        .collect()
}

/// An optional array of objects: absent means empty (KR-319).
fn list<'a>(i: &Inputs<'a>, k: &str) -> Result<Vec<Inputs<'a>>> {
    if i.opt(k).is_some() {
        objects(i, k)
    } else {
        Ok(Vec::new())
    }
}

fn string(i: &Inputs, k: &str) -> Result<String> {
    i.str(k).map(str::to_string)
}

fn opt_string(i: &Inputs, k: &str) -> Result<Option<String>> {
    i.opt(k).map(|_| string(i, k)).transpose()
}

fn object<'a>(i: &Inputs<'a>, k: &str) -> Result<Inputs<'a>> {
    match i.req(k)? {
        v @ Json::Obj(_) => Ok(Inputs::new(v)),
        _ => i.fail(k, "expected an object"),
    }
}

fn cva_ba(i: &Inputs) -> Result<Outcome> {
    let sectors = cva::sectors();
    let sectors: Vec<&str> = sectors.iter().map(String::as_str).collect();
    let mut cps = Vec::new();
    for c in objects(i, "counterparties")? {
        let netting_sets = objects(&c, "netting_sets")?
            .iter()
            .map(|n| {
                Ok(cva::NettingSet {
                    ead: n.f64("ead")?,
                    m: n.f64("m")?,
                    imm: n.bool_or("imm", false)?,
                })
            })
            .collect::<Result<Vec<_>>>()?;
        cps.push(cva::Counterparty {
            id: string(&c, "id")?,
            sector: choice(&c, "sector", &sectors)?,
            quality: choice(&c, "quality", &cva::QUALITIES)?,
            netting_sets,
        });
    }
    let version = choice(i, "version", &cva::VERSIONS)?;
    let mut single = Vec::new();
    for h in list(i, "single_name_hedges")? {
        single.push(cva::SingleNameHedge {
            counterparty: string(&h, "counterparty")?,
            relation: choice(&h, "relation", &cva::RELATION_NAMES)?,
            sector: choice(&h, "sector", &sectors)?,
            quality: choice(&h, "quality", &cva::QUALITIES)?,
            m: h.f64("m")?,
            notional: h.f64("notional")?,
        });
    }
    let mut index = Vec::new();
    for h in list(i, "index_hedges")? {
        let constituents = objects(&h, "constituents")?
            .iter()
            .map(|k| {
                Ok(cva::Constituent {
                    sector: choice(k, "sector", &sectors)?,
                    quality: choice(k, "quality", &cva::QUALITIES)?,
                    weight: k.f64("weight")?,
                })
            })
            .collect::<Result<Vec<_>>>()?;
        index.push(cva::IndexHedge {
            m: h.f64("m")?,
            notional: h.f64("notional")?,
            constituents,
        });
    }
    i.gate()?;
    let r = cva::ba_cva(&cps, &version, &single, &index)?;
    let rows = r
        .counterparties
        .iter()
        .map(|c| {
            obj([
                ("id", c.id.as_str().into()),
                ("scva", c.scva.into()),
                ("snh", c.snh.into()),
                ("hma", c.hma.into()),
                (
                    "netting_sets",
                    Json::Arr(c.dfs.iter().map(|d| obj([("df", (*d).into())])).collect()),
                ),
            ])
        })
        .collect();
    plain(obj([
        ("version", r.version.into()),
        ("counterparties", Json::Arr(rows)),
        ("ih", r.ih.into()),
        ("k_reduced", r.k_reduced.into()),
        ("k_hedged", r.k_hedged.into()),
        ("k_full", r.k_full.into()),
        ("capital", r.capital.into()),
        ("rwa", r.rwa.into()),
        ("label", cva::LABEL.into()),
    ]))
}

fn sensitivity(cls: &str, kind: &str, s: &Inputs) -> Result<cva::Sensitivity> {
    let factor = if cls == "CCS" {
        let f = object(s, "factor")?;
        let tenors = cva::ccs_tenors();
        let tenors: Vec<&str> = tenors.iter().map(String::as_str).collect();
        cva::Factor::Credit(cva::CreditFactor {
            name: string(&f, "name")?,
            tenor: choice(&f, "tenor", &tenors)?,
            quality: choice(&f, "quality", &cva::QUALITIES)?,
            legal_group: opt_string(&f, "legal_group")?,
            index: opt_string(&f, "index")?,
            series: opt_string(&f, "series")?,
        })
    } else if cls == "IR" {
        let allowed = if kind == "DELTA" {
            cva::ir_delta_factors()
        } else {
            cva::IR_VEGA_FACTORS.iter().map(|x| (*x).to_string()).collect()
        };
        let allowed: Vec<&str> = allowed.iter().map(String::as_str).collect();
        cva::Factor::Name(choice(s, "factor", &allowed)?)
    } else {
        cva::Factor::Name(string(s, "factor")?)
    };
    Ok(cva::Sensitivity {
        bucket: string(s, "bucket")?,
        factor,
        s_cva: s.f64("s_cva")?,
        s_hdg: s.f64("s_hdg")?,
    })
}

fn cva_sa(i: &Inputs) -> Result<Outcome> {
    let c = object(i, "classes")?;
    let Json::Obj(fields) = c.0 else {
        return i.fail("classes", "expected an object");
    };
    let mut classes = Vec::with_capacity(fields.len());
    for (key, _) in fields {
        // CCS.VEGA is read here and refused by the core as E_INPUT (cva-capital.md, Errors).
        let (cls, kind) = key.split_once('.').unwrap_or((key.as_str(), ""));
        if !(cva::RISK_CLASSES.contains(&cls) && cva::KINDS.contains(&kind)) {
            return i.fail("classes", "class key not listed");
        }
        let items = objects(&c, key)?
            .iter()
            .map(|s| sensitivity(cls, kind, s))
            .collect::<Result<Vec<_>>>()?;
        classes.push((key.clone(), items));
    }
    let reporting = string(i, "reporting_currency")?;
    let m_cva = i.f64_or("m_cva", 1.0)?;
    i.gate()?;
    let r = cva::sa_cva(&classes, &reporting, m_cva)?;
    let out = r
        .classes
        .iter()
        .map(|(key, cr)| {
            let buckets = cr
                .buckets
                .iter()
                .map(|b| {
                    obj([
                        ("bucket", b.bucket.as_str().into()),
                        ("k_b", b.k_b.into()),
                        ("s_b", b.s_b.into()),
                        ("sum_ws", b.sum_ws.into()),
                        ("floored", b.floored.into()),
                    ])
                })
                .collect();
            (
                key.clone(),
                obj([("buckets", Json::Arr(buckets)), ("k", cr.k.into())]),
            )
        })
        .collect();
    plain(obj([
        ("classes", Json::Obj(out)),
        ("m_cva", r.m_cva.into()),
        ("total", r.total.into()),
        ("rwa", r.rwa.into()),
        ("label", cva::LABEL.into()),
    ]))
}

fn leverage(i: &Inputs) -> Result<Outcome> {
    let tier1 = i.f64("tier1")?;
    let on_balance = if i.opt("on_balance").is_some() {
        i.reals("on_balance")?
    } else {
        Vec::new()
    };
    let derivatives = list(i, "derivatives")?
        .iter()
        .map(|d| {
            Ok(lev::DerivativeSet {
                v: d.f64("v")?,
                pfe: d.f64("pfe")?,
                cvm_received: d.f64_or("cvm_received", 0.0)?,
                cvm_provided: d.f64_or("cvm_provided", 0.0)?,
            })
        })
        .collect::<Result<Vec<_>>>()?;
    let written = list(i, "written_credit_derivatives")?
        .iter()
        .map(|w| {
            Ok(lev::WrittenCreditDerivative {
                notional: w.f64("notional")?,
                fair_value: w.f64("fair_value")?,
                purchased_offset: w.f64_or("purchased_offset", 0.0)?,
            })
        })
        .collect::<Result<Vec<_>>>()?;
    let sfts = list(i, "sfts")?
        .iter()
        .map(|s| {
            Ok(lev::Sft {
                gross_assets: s.f64("gross_assets")?,
                mna: s.bool("mna")?,
                exposures: s.reals("exposures")?,
                collateral: s.reals("collateral")?,
            })
        })
        .collect::<Result<Vec<_>>>()?;
    let categories = lev::ccf_category_names();
    let off_balance = list(i, "off_balance")?
        .iter()
        .map(|o| {
            Ok(lev::OffBalance {
                notional: o.f64("notional")?,
                ccf_category: choice(o, "ccf_category", &categories)?,
            })
        })
        .collect::<Result<Vec<_>>>()?;
    i.gate()?;
    let r = lev::leverage(tier1, &on_balance, &derivatives, &written, &sfts, &off_balance)?;
    plain(obj([
        ("on_balance", r.on_balance.into()),
        ("derivatives", r.derivatives.into()),
        ("derivative_netting_sets", r.derivative_netting_sets.into()),
        (
            "written_credit_derivatives",
            r.written_credit_derivatives.into(),
        ),
        ("sfts", r.sfts.into()),
        ("off_balance", r.off_balance.into()),
        ("exposure", r.exposure.into()),
        ("ratio", r.ratio.into()),
        ("meets_minimum", r.meets_minimum.into()),
        ("label", lev::LEVERAGE_LABEL.into()),
    ]))
}

fn large_exposures(i: &Inputs) -> Result<Outcome> {
    let tier1 = i.f64("tier1")?;
    let bank_gsib = i.bool_or("bank_gsib", false)?;
    let cps = objects(i, "counterparties")?
        .iter()
        .map(|c| {
            Ok(lev::LeCounterparty {
                id: string(c, "id")?,
                group: opt_string(c, "group")?,
                gsib: c.bool_or("gsib", false)?,
                exempt: c.bool_or("exempt", false)?,
            })
        })
        .collect::<Result<Vec<_>>>()?;
    let bb = list(i, "banking_book")?
        .iter()
        .map(|b| {
            Ok(lev::BankingBookExposure {
                counterparty: string(b, "counterparty")?,
                value: b.f64("value")?,
            })
        })
        .collect::<Result<Vec<_>>>()?;
    let obs = list(i, "off_balance")?
        .iter()
        .map(|o| {
            Ok(lev::OffBalanceExposure {
                counterparty: string(o, "counterparty")?,
                notional: o.f64("notional")?,
                ccf: o.f64("ccf")?,
            })
        })
        .collect::<Result<Vec<_>>>()?;
    let crm = list(i, "crm")?
        .iter()
        .map(|p| {
            Ok(lev::Protection {
                counterparty: string(p, "counterparty")?,
                provider: string(p, "provider")?,
                protected: p.f64("protected")?,
            })
        })
        .collect::<Result<Vec<_>>>()?;
    let tb = list(i, "trading_book")?
        .iter()
        .map(|t| {
            // maturity_years, cash_equity and lgd_applies are read and ignored (KR-322).
            t.opt_f64("maturity_years")?;
            t.bool_or("cash_equity", false)?;
            t.bool_or("lgd_applies", true)?;
            Ok(lev::TradingPosition {
                id: string(t, "id")?,
                counterparty: string(t, "counterparty")?,
                seniority: choice(t, "seniority", &lev::SENIORITIES)?,
                notional: t.f64("notional")?,
                market_value: t.f64("market_value")?,
            })
        })
        .collect::<Result<Vec<_>>>()?;
    i.gate()?;
    let r = lev::large_exposures(tier1, &cps, &bb, &obs, &crm, &tb, bank_gsib)?;
    let rows = r
        .counterparties
        .iter()
        .map(|c| {
            obj([
                ("id", c.id.as_str().into()),
                ("banking_book", c.banking_book.into()),
                ("off_balance", c.off_balance.into()),
                ("trading_book_net_long", c.trading_book_net_long.into()),
                ("trading_book_net_short", c.trading_book_net_short.into()),
                ("protected", c.protected.into()),
                ("received", c.received.into()),
                ("exposure", c.exposure.into()),
            ])
        })
        .collect();
    let groups = r
        .groups
        .iter()
        .map(|g| {
            obj([
                ("group", g.group.as_str().into()),
                ("members", g.members.clone().into()),
                ("exposure", g.exposure.into()),
                ("share", g.share.into()),
                ("large", g.large.into()),
                ("limit", g.limit.into()),
                ("breach", g.breach.into()),
                ("exempt", g.exempt.into()),
            ])
        })
        .collect();
    plain(obj([
        ("counterparties", Json::Arr(rows)),
        ("groups", Json::Arr(groups)),
        ("report", r.report.into()),
        ("label", lev::LARGE_EXPOSURES_LABEL.into()),
    ]))
}
