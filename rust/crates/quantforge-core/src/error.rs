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
