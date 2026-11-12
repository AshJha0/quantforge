//! Stage I wave 2 credit and correlation hedges (`08-hedging/credit-and-correlation-hedges.md`):
//! unit tests and the property tests the spec names.
#![allow(clippy::unwrap_used)] // tests may unwrap (G9)
use proptest::prelude::*;
use quantforge_core::credit::{CdsTrade, Hazard};
use quantforge_core::curve::{Curve, CurveInput, Interpolation};
use quantforge_core::dates::Date;
use quantforge_core::hedge_cross::{
    CorrKind, CorrLeg, CorrMarket, CorrTarget, CreditMarket, CreditTarget, correlation_hedge,
    credit_hedge,
};

fn date(s: &str) -> Date {
    Date::parse(s).unwrap()
}

struct Credit {
    curve: Curve,
    pillars: Vec<Date>,
    hazard: Hazard,
}

fn credit() -> Credit {
    let t = date("2026-11-06");
    let input = CurveInput {
        as_of: t,
        interpolation: Interpolation::LogLinearDf,
        pillars: vec![(date("2046-11-06"), 0.458_161_174_870_904)],
        jumps: Vec::new(),
    };
    let hazard = Hazard::new(
        t,
        &[
            (date("2027-12-20"), 0.988_761_295_505_626_6),
            (date("2029-12-20"), 0.953_364_785_654_785_2),
            (date("2031-12-20"), 0.898_945_052_959_471_5),
            (date("2033-12-20"), 0.845_045_306_240_185_8),
            (date("2036-12-20"), 0.763_614_811_302_842_9),
        ],
    )
    .unwrap();
    Credit {
        curve: Curve::new(&input).unwrap(),
        pillars: vec![date("2046-11-06")],
        hazard,
    }
}

fn market(c: &Credit, recovery: f64) -> CreditMarket<'_> {
    CreditMarket {
        trade_date: date("2026-11-06"),
        discount: &c.curve,
        discount_pillars: &c.pillars,
        hazard: &c.hazard,
        recovery,
    }
}

fn sold(maturity: &str, notional: f64) -> CdsTrade {
    CdsTrade {
        maturity: date(maturity),
        coupon: 0.01,
        notional,
        buy: false,
    }
}

fn code<T: std::fmt::Debug>(r: quantforge_core::error::Result<T>) -> &'static str {
    r.unwrap_err().code
}

#[test]
fn credit_targets_parse() {
    assert_eq!(CreditTarget::parse("CS01", 5).unwrap(), CreditTarget::Cs01);
    assert_eq!(CreditTarget::parse("JTD", 5).unwrap(), CreditTarget::Jtd);
    assert_eq!(
        CreditTarget::parse("BUCKET_5", 5).unwrap(),
        CreditTarget::Bucket(5)
    );
    for bad in [
        "BUCKET_0",
        "BUCKET_6",
        "BUCKET_",
        "BUCKET_+1",
        "cs01",
        "RHO",
    ] {
        assert_eq!(code(CreditTarget::parse(bad, 5)), "E_INPUT", "{bad}");
    }
}

#[test]
fn own_contract_returns_the_book_notional_and_zero_risk() {
    let c = credit();
    let m = market(&c, 0.4);
    let book = [sold("2033-12-20", 1e7)];
    let s = credit_hedge(&m, &book, &[(date("2033-12-20"), 0.01)], &["CS01"]).unwrap();
    assert!((s.notionals[0] - 1e7).abs() < 1e-6);
    assert!(s.after.cs01.abs() < 1e-8 && s.after.jtd.abs() < 1e-6);
    // The last section lies past the 7Y maturity: exactly zero bucket risk.
    assert_eq!(s.book.buckets[4], 0.0);
    // A bought book is the mirror image.
    let bought = [CdsTrade {
        buy: true,
        ..book[0]
    }];
    let t = credit_hedge(&m, &bought, &[(date("2033-12-20"), 0.01)], &["JTD"]).unwrap();
    assert!((t.notionals[0] + 1e7).abs() < 1e-6);
    assert!((t.book.pv + s.book.pv).abs() < 1e-9);
}

#[test]
fn credit_checks_in_order() {
    let c = credit();
    let m = market(&c, 0.4);
    let book = [sold("2033-12-20", 1e7)];
    let five = [(date("2031-12-20"), 0.01)];
    let two = [(date("2031-12-20"), 0.01), (date("2029-12-20"), 0.01)];
    assert_eq!(code(credit_hedge(&m, &[], &five, &["CS01"])), "E_INPUT");
    assert_eq!(code(credit_hedge(&m, &book, &two, &["CS01"])), "E_INPUT");
    assert_eq!(
        code(credit_hedge(&m, &book, &two, &["CS01", "CS01"])),
        "E_INPUT"
    );
    assert_eq!(
        code(credit_hedge(&m, &book, &five, &["BUCKET_6"])),
        "E_INPUT"
    );
    let today = [(date("2026-11-06"), 0.01)];
    assert_eq!(code(credit_hedge(&m, &book, &today, &["CS01"])), "E_INPUT");
    assert_eq!(
        code(credit_hedge(&market(&c, 1.0), &book, &five, &["CS01"])),
        "E_DOMAIN"
    );
    assert_eq!(
        code(credit_hedge(&market(&c, f64::NAN), &book, &five, &["CS01"])),
        "E_DOMAIN"
    );
    let negative = [sold("2033-12-20", -1.0)];
    assert_eq!(
        code(credit_hedge(&m, &negative, &five, &["CS01"])),
        "E_DOMAIN"
    );
    let bad_coupon = [(date("2031-12-20"), -0.01)];
    assert_eq!(
        code(credit_hedge(&m, &book, &bad_coupon, &["CS01"])),
        "E_DOMAIN"
    );
    let twice = [(date("2031-12-20"), 0.01), (date("2031-12-20"), 0.01)];
    assert_eq!(
        code(credit_hedge(&m, &book, &twice, &["CS01", "JTD"])),
        "E_SINGULAR"
    );
    let short = [(date("2027-12-20"), 0.01), (date("2029-12-20"), 0.01)];
    assert_eq!(
        code(credit_hedge(&m, &book, &short, &["BUCKET_4", "BUCKET_5"])),
        "E_SINGULAR"
    );
}

#[test]
fn bucket_cs01s_add_up_to_the_parallel_cs01_to_first_order() {
    let c = credit();
    let m = market(&c, 0.4);
    let book = [sold("2036-12-20", 1e7)];
    let s = credit_hedge(&m, &book, &[(date("2031-12-20"), 0.01)], &["CS01"]).unwrap();
    let sum: f64 = s.book.buckets.iter().sum();
    assert!(
        (sum - s.book.cs01).abs() < 1e-3 * s.book.cs01.abs(),
        "{sum} {}",
        s.book.cs01
    );
    assert!(s.after.cs01.abs() < 1e-8);
}

const MARKET: CorrMarket = CorrMarket {
    spot1: 100.0,
    spot2: 95.0,
    rate: 0.03,
    yield1: 0.01,
    yield2: 0.02,
    vol1: 0.25,
    vol2: 0.2,
    correlation: 0.6,
};

fn exchange(expiry: f64) -> CorrLeg {
    CorrLeg {
        kind: CorrKind::Exchange,
        fields: vec![
            ("quantity1".into(), 1.0),
            ("quantity2".into(), 1.0),
            ("expiry_years".into(), expiry),
        ],
    }
}

fn vanilla(kind: CorrKind, strike: f64, expiry: f64) -> CorrLeg {
    CorrLeg {
        kind,
        fields: vec![("strike".into(), strike), ("expiry_years".into(), expiry)],
    }
}

fn underlying(kind: CorrKind) -> CorrLeg {
    CorrLeg {
        kind,
        fields: Vec::new(),
    }
}

#[test]
fn correlation_and_vega_need_a_vanilla() {
    let book = [(exchange(1.0), -1000.0), (exchange(2.0), 400.0)];
    let targets = [CorrTarget::Correlation, CorrTarget::Vega1];
    let only = [exchange(0.5), exchange(1.5)];
    // I-17: exchange options alone have proportional vega and correlation rows.
    assert_eq!(
        code(correlation_hedge(&MARKET, &book, &only, &targets)),
        "E_SINGULAR"
    );
    let mixed = [exchange(0.5), vanilla(CorrKind::Call1, 100.0, 1.0)];
    let r = correlation_hedge(&MARKET, &book, &mixed, &targets).unwrap();
    let scale = r.before.iter().fold(1.0f64, |m, v| m.max(v.abs()));
    assert!(r.after[4].abs() < 1e-10 * scale && r.after[2].abs() < 1e-10 * scale);
    let all = [
        underlying(CorrKind::Underlying1),
        underlying(CorrKind::Underlying2),
        vanilla(CorrKind::Put1, 95.0, 0.75),
        vanilla(CorrKind::Call2, 90.0, 1.25),
        exchange(0.5),
    ];
    let every = [
        CorrTarget::Delta1,
        CorrTarget::Delta2,
        CorrTarget::Vega1,
        CorrTarget::Vega2,
        CorrTarget::Correlation,
    ];
    let r = correlation_hedge(&MARKET, &book, &all, &every).unwrap();
    assert!(r.after.iter().all(|v| v.abs() < 1e-10 * scale));
}

#[test]
fn correlation_checks_in_order() {
    let book = [(exchange(1.0), -1000.0)];
    let c = |m: &CorrMarket, b: &[(CorrLeg, f64)], h: &[CorrLeg], t: &[CorrTarget]| {
        code(correlation_hedge(m, b, h, t))
    };
    let delta = [CorrTarget::Delta1];
    let mut extra = underlying(CorrKind::Underlying1);
    extra.fields.push(("expiry_years".into(), 1.0));
    assert_eq!(c(&MARKET, &book, &[extra.clone()], &delta), "E_INPUT");
    let mut nan = MARKET;
    nan.vol2 = f64::NAN;
    // F-2 before the key checks.
    assert_eq!(c(&nan, &book, &[extra], &delta), "E_DOMAIN");
    let short = CorrLeg {
        kind: CorrKind::Exchange,
        fields: vec![("quantity1".into(), 1.0), ("quantity2".into(), 1.0)],
    };
    assert_eq!(
        c(
            &MARKET,
            &[(short, 1.0)],
            &[underlying(CorrKind::Underlying1)],
            &delta
        ),
        "E_INPUT"
    );
    assert_eq!(c(&MARKET, &book, &[], &[]), "E_INPUT");
    let two = [
        underlying(CorrKind::Underlying1),
        underlying(CorrKind::Underlying2),
    ];
    assert_eq!(c(&MARKET, &book, &two, &delta), "E_INPUT");
    assert_eq!(
        c(
            &MARKET,
            &book,
            &two,
            &[CorrTarget::Delta1, CorrTarget::Delta1]
        ),
        "E_INPUT"
    );
    let mut high = MARKET;
    high.correlation = 1.01;
    assert_eq!(c(&high, &book, &two[..1], &delta), "E_DOMAIN");
    let mut flat = MARKET;
    flat.vol1 = 0.0;
    assert_eq!(c(&flat, &book, &two[..1], &delta), "E_DOMAIN");
    let mut same = MARKET;
    (same.vol1, same.vol2, same.correlation) = (0.2, 0.2, 1.0);
    assert_eq!(c(&same, &book, &two[..1], &delta), "E_DOMAIN");
    // Without an exchange option a zero spread volatility is harmless.
    let call = [(vanilla(CorrKind::Call1, 100.0, 1.0), 10.0)];
    assert!(correlation_hedge(&same, &call, &two[..1], &delta).is_ok());
    // rho = 1 with unequal vols is regular.
    let mut one = MARKET;
    one.correlation = 1.0;
    assert!(correlation_hedge(&one, &book, &two[..1], &delta).is_ok());
    let strike0 = [vanilla(CorrKind::Put2, 0.0, 1.0)];
    assert_eq!(c(&MARKET, &book, &strike0, &delta), "E_DOMAIN");
    assert_eq!(
        c(
            &MARKET,
            &book,
            &two,
            &[CorrTarget::Correlation, CorrTarget::Delta1]
        ),
        "E_SINGULAR"
    );
}

proptest! {
    #![proptest_config(ProptestConfig::with_cases(128))]

    #[test]
    fn long_exchange_has_negative_correlation01_and_vanillas_none(
        spot1 in 50.0..150.0_f64,
        spot2 in 50.0..150.0_f64,
        vol1 in 0.05..0.6_f64,
        vol2 in 0.05..0.6_f64,
        rho in -0.95..0.95_f64,
        expiry in 0.1..3.0_f64,
        strike in 60.0..140.0_f64,
    ) {
        let m = CorrMarket { spot1, spot2, vol1, vol2, correlation: rho, ..MARKET };
        let delta = [CorrTarget::Delta1];
        let u = [underlying(CorrKind::Underlying1)];
        let r = correlation_hedge(&m, &[(exchange(expiry), 1.0)], &u, &delta).unwrap();
        prop_assert!(r.before[4] < 0.0);
        for kind in [CorrKind::Call1, CorrKind::Put1, CorrKind::Call2, CorrKind::Put2] {
            let r = correlation_hedge(&m, &[(vanilla(kind, strike, expiry), 1.0)], &u, &delta).unwrap();
            prop_assert_eq!(r.before[4], 0.0);
        }
    }

    #[test]
    fn credit_hedge_zeroes_its_targets(
        notional in 1e5..1e8_f64,
        coupon in prop_oneof![Just(0.01), Just(0.05)],
        recovery in 0.0..0.8_f64,
        targets in prop_oneof![
            Just(vec!["CS01", "JTD"]),
            Just(vec!["BUCKET_2", "BUCKET_3"]),
            Just(vec!["JTD", "BUCKET_1"]),
        ],
    ) {
        let c = credit();
        let m = market(&c, recovery);
        let book = [CdsTrade { coupon, ..sold("2033-12-20", notional) }];
        let hedges = [(date("2029-12-20"), 0.01), (date("2031-12-20"), 0.05)];
        let s = credit_hedge(&m, &book, &hedges, &targets).unwrap();
        let scale = s.book.jtd.abs().max(s.book.cs01.abs()).max(1.0);
        for t in &targets {
            let v = match CreditTarget::parse(t, 5).unwrap() {
                CreditTarget::Cs01 => s.after.cs01,
                CreditTarget::Jtd => s.after.jtd,
                CreditTarget::Bucket(k) => s.after.buckets[k - 1],
            };
            prop_assert!(v.abs() < 1e-9 * scale, "{t} {v}");
        }
    }
}
