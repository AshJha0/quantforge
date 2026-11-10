//! Reverse-mode algorithmic differentiation on a tape (ruling F-29, the Rust reference method).
//!
//! Each operation records its value's local partials against at most two parents. A reverse
//! sweep from one output gives the adjoint of every recorded variable. An input the output does
//! not depend on keeps an adjoint of exactly 0.
use std::cell::RefCell;
use std::ops::{Add, Div, Mul, Neg, Sub};

#[derive(Debug, Clone, Copy)]
struct Node {
    parents: [(usize, f64); 2],
    count: u8,
}

/// The tape. Variables borrow it, so a tape outlives every variable recorded on it.
#[derive(Debug, Default)]
pub struct Tape {
    nodes: RefCell<Vec<Node>>,
}

/// A recorded variable: its value and its index on the tape.
#[derive(Debug, Clone, Copy)]
pub struct Var<'t> {
    tape: &'t Tape,
    idx: usize,
    pub val: f64,
}

impl Tape {
    pub fn new() -> Tape {
        Tape::default()
    }

    fn push(&self, parents: [(usize, f64); 2], count: u8) -> usize {
        let mut n = self.nodes.borrow_mut();
        n.push(Node { parents, count });
        n.len() - 1
    }

    /// An independent input.
    pub fn var(&self, val: f64) -> Var<'_> {
        Var {
            tape: self,
            idx: self.push([(0, 0.0); 2], 0),
            val,
        }
    }

    /// A constant: recorded with no parents, so it carries no derivative.
    pub fn constant(&self, val: f64) -> Var<'_> {
        self.var(val)
    }

    pub fn len(&self) -> usize {
        self.nodes.borrow().len()
    }

    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// Adjoints of every variable for the output `out` (seed 1).
    pub fn adjoints(&self, out: Var<'_>) -> Vec<f64> {
        let nodes = self.nodes.borrow();
        let mut bar = vec![0.0; nodes.len()];
        bar[out.idx] = 1.0;
        for i in (0..=out.idx).rev() {
            let b = bar[i];
            if b == 0.0 {
                continue;
            }
            let n = nodes[i];
            for &(p, d) in &n.parents[..n.count as usize] {
                bar[p] += b * d;
            }
        }
        bar
    }
}

impl<'t> Var<'t> {
    fn unary(self, val: f64, d: f64) -> Var<'t> {
        Var {
            tape: self.tape,
            idx: self.tape.push([(self.idx, d), (0, 0.0)], 1),
            val,
        }
    }

    fn binary(self, o: Var<'t>, val: f64, da: f64, db: f64) -> Var<'t> {
        Var {
            tape: self.tape,
            idx: self.tape.push([(self.idx, da), (o.idx, db)], 2),
            val,
        }
    }

    pub fn tape(&self) -> &'t Tape {
        self.tape
    }

    pub fn idx(&self) -> usize {
        self.idx
    }

    #[must_use]
    pub fn exp(self) -> Var<'t> {
        let e = self.val.exp();
        self.unary(e, e)
    }

    #[must_use]
    pub fn ln(self) -> Var<'t> {
        self.unary(self.val.ln(), 1.0 / self.val)
    }
}

impl<'t> Add for Var<'t> {
    type Output = Var<'t>;
    fn add(self, o: Var<'t>) -> Var<'t> {
        self.binary(o, self.val + o.val, 1.0, 1.0)
    }
}

impl<'t> Sub for Var<'t> {
    type Output = Var<'t>;
    fn sub(self, o: Var<'t>) -> Var<'t> {
        self.binary(o, self.val - o.val, 1.0, -1.0)
    }
}

impl<'t> Mul for Var<'t> {
    type Output = Var<'t>;
    fn mul(self, o: Var<'t>) -> Var<'t> {
        self.binary(o, self.val * o.val, o.val, self.val)
    }
}

impl<'t> Div for Var<'t> {
    type Output = Var<'t>;
    fn div(self, o: Var<'t>) -> Var<'t> {
        let q = self.val / o.val;
        self.binary(o, q, 1.0 / o.val, -q / o.val)
    }
}

impl<'t> Neg for Var<'t> {
    type Output = Var<'t>;
    fn neg(self) -> Var<'t> {
        self.unary(-self.val, -1.0)
    }
}

impl<'t> Add<f64> for Var<'t> {
    type Output = Var<'t>;
    fn add(self, c: f64) -> Var<'t> {
        self.unary(self.val + c, 1.0)
    }
}

impl<'t> Sub<f64> for Var<'t> {
    type Output = Var<'t>;
    fn sub(self, c: f64) -> Var<'t> {
        self.unary(self.val - c, 1.0)
    }
}

impl<'t> Mul<f64> for Var<'t> {
    type Output = Var<'t>;
    fn mul(self, c: f64) -> Var<'t> {
        self.unary(self.val * c, c)
    }
}

impl<'t> Div<f64> for Var<'t> {
    type Output = Var<'t>;
    fn div(self, c: f64) -> Var<'t> {
        self.unary(self.val / c, 1.0 / c)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn gradient_of_a_small_expression() {
        let t = Tape::new();
        let (x, y) = (t.var(1.5), t.var(-0.25));
        // f = exp(x y) / (x - y) + ln(x)
        let f = (x * y).exp() / (x - y) + x.ln();
        let bar = t.adjoints(f);
        let (xv, yv) = (1.5f64, -0.25f64);
        let e = (xv * yv).exp();
        let dx = (yv * e * (xv - yv) - e) / (xv - yv).powi(2) + 1.0 / xv;
        let dy = (xv * e * (xv - yv) + e) / (xv - yv).powi(2);
        assert!((bar[x.idx()] - dx).abs() < 1e-15);
        assert!((bar[y.idx()] - dy).abs() < 1e-15);
        let z = t.var(3.0);
        let g = x * 2.0;
        assert_eq!(t.adjoints(g)[z.idx()], 0.0);
    }
}
