//! Error type carrying the contract's error codes.

#[derive(Debug, Clone, PartialEq)]
pub struct QfError {
    pub code: &'static str,
    pub message: String,
    pub field: Option<String>,
}

pub type Result<T> = std::result::Result<T, QfError>;

pub fn err(code: &'static str, message: impl Into<String>) -> QfError {
    QfError {
        code,
        message: message.into(),
        field: None,
    }
}

pub fn fail<T>(code: &'static str, message: impl Into<String>) -> Result<T> {
    Err(err(code, message))
}

/// E1: every public numeric input is finite. `x < 0.0` style checks let NaN through, so each
/// public entry point that returns `Result` checks its inputs first. `-0.0` is finite.
pub trait Finite {
    fn is_all_finite(&self) -> bool;
}

impl Finite for f64 {
    fn is_all_finite(&self) -> bool {
        f64::is_finite(*self)
    }
}

macro_rules! always_finite {
    ($($t:ty),*) => {$(
        impl Finite for $t {
            fn is_all_finite(&self) -> bool {
                true
            }
        }
    )*};
}
always_finite!(
    bool,
    i32,
    i64,
    u32,
    u64,
    usize,
    str,
    String,
    crate::dates::Date
);

impl<T: Finite + ?Sized> Finite for &T {
    fn is_all_finite(&self) -> bool {
        (**self).is_all_finite()
    }
}

impl<T: Finite> Finite for [T] {
    fn is_all_finite(&self) -> bool {
        self.iter().all(Finite::is_all_finite)
    }
}

impl<T: Finite, const N: usize> Finite for [T; N] {
    fn is_all_finite(&self) -> bool {
        self.iter().all(Finite::is_all_finite)
    }
}

impl<T: Finite> Finite for Vec<T> {
    fn is_all_finite(&self) -> bool {
        self.iter().all(Finite::is_all_finite)
    }
}

impl<T: Finite> Finite for Option<T> {
    fn is_all_finite(&self) -> bool {
        self.as_ref().is_none_or(Finite::is_all_finite)
    }
}

impl<A: Finite, B: Finite> Finite for (A, B) {
    fn is_all_finite(&self) -> bool {
        self.0.is_all_finite() && self.1.is_all_finite()
    }
}

impl<A: Finite, B: Finite, C: Finite> Finite for (A, B, C) {
    fn is_all_finite(&self) -> bool {
        self.0.is_all_finite() && self.1.is_all_finite() && self.2.is_all_finite()
    }
}

/// `E_DOMAIN` naming `field` when any number in `x` is NaN or infinite.
pub fn finite<T: Finite + ?Sized>(field: &str, x: &T) -> Result<()> {
    if x.is_all_finite() {
        Ok(())
    } else {
        Err(QfError {
            code: "E_DOMAIN",
            message: format!("{field} must be finite"),
            field: Some(field.to_string()),
        })
    }
}

#[cfg(test)]
mod finite_tests {
    use super::*;

    #[test]
    fn edges() {
        for bad in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            assert_eq!(finite("x", &bad).unwrap_err().code, "E_DOMAIN");
            assert!(finite("x", &[1.0, bad][..]).is_err());
            assert!(finite("x", &Some(bad)).is_err());
            assert!(finite("x", &(1_i64, bad)).is_err());
        }
        for good in [0.0, -0.0, f64::MAX, f64::MIN, f64::MIN_POSITIVE, 5e-324] {
            assert!(finite("x", &good).is_ok());
        }
        assert!(finite("x", &None::<f64>).is_ok());
        assert!(finite("x", &Vec::<f64>::new()).is_ok());
        assert_eq!(
            finite("v", &f64::NAN).unwrap_err().field.as_deref(),
            Some("v")
        );
    }
}
