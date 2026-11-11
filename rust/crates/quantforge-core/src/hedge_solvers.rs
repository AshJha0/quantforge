//! Hedge solvers (`08-hedging/hedge-solvers.md`, stage I wave 1): constrained least squares,
//! integer contracts, minimum-variance ratios, Greek and beta hedges, residual risk.
//!
//! Every rank or singularity decision compares with `1e-12` times the largest singular value,
//! eigenvalue or pivot of the stated matrix (ruling I-3).

use crate::error::{Result, fail, finite};
use crate::linalg::{Matrix, eigen_pairs, eigen_symmetric, singular_values, solve};
use crate::stats::{normal_cdf, normal_pdf};

/// The one relative threshold of ruling I-3.
const THRESHOLD: f64 = 1e-12;

/// Relative regularisation of the split problem that finds the sign state of the wave 4a
/// problem. Only the sign state is taken from it; the answer is re-solved exactly.
const SPLIT_DELTA: f64 = 1e-6;

/// Dependence test of the active-set method on the split problem, whose Hessian has condition
/// up to `2 / SPLIT_DELTA`: a new constraint whose primal step is below this share of its
/// full-space curvature is treated as dependent on the active set.
const SPLIT_DEPENDENCE: f64 = 1e-8;

/// What `hedge.qp.solve` does with a singular reduced Hessian (ruling I-5).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Singular {
    /// `E_SINGULAR` (the default).
    Error,
    /// The minimum Euclidean-norm minimiser.
    MinNorm,
}

/// Inputs of `hedge.qp.solve`. `lower` and `upper` hold `None` for "no bound".
#[derive(Debug, Clone)]
pub struct QpProblem<'a> {
    pub a: &'a Matrix,
    pub b: &'a [f64],
    pub weights: &'a [f64],
    pub ridge: f64,
    /// `(eq_matrix, eq_rhs)`; the shape check needs both present or both absent.
    pub eq_matrix: Option<&'a Matrix>,
    pub eq_rhs: Option<&'a [f64]>,
    pub lower: Option<&'a [Option<f64>]>,
    pub upper: Option<&'a [Option<f64>]>,
    pub singular: Singular,
    /// The wave 4a inputs; all absent for the wave 1 problem.
    pub costs: Costs<'a>,
}

/// The optional cost and margin inputs of `hedge.qp.solve` (wave 4a, rulings I-24 to I-27):
/// `cost_weight * sum_j (half_spreads_j |x_j| + impact_j x_j^2)` joins the objective, and
/// `sum_j margin_rates_j |x_j| <= margin_limit` the constraints.
#[derive(Debug, Clone, Copy, Default)]
pub struct Costs<'a> {
    pub half_spreads: Option<&'a [f64]>,
    pub impact: Option<&'a [f64]>,
    /// Default 1.
    pub cost_weight: Option<f64>,
    pub margin_rates: Option<&'a [f64]>,
    pub margin_limit: Option<f64>,
}

impl Costs<'_> {
    /// Whether any new input is given (I-27 output rule).
    #[must_use]
    pub fn any(&self) -> bool {
        self.half_spreads.is_some()
            || self.impact.is_some()
            || self.cost_weight.is_some()
            || self.margin_rates.is_some()
            || self.margin_limit.is_some()
    }
}

/// Outputs of `hedge.qp.solve`.
#[derive(Debug, Clone, PartialEq)]
pub struct QpSolution {
    pub x: Vec<f64>,
    pub residual: Vec<f64>,
    pub objective: f64,
    /// Eigenvalues of the reduced Hessian above the threshold.
    pub rank: usize,
    /// `sum w r^2 + ridge |x|^2`, present with any cost input (I-27).
    pub risk: Option<f64>,
    /// `C(x)`, present with any cost input.
    pub cost: Option<f64>,
    /// `sum m |x|`, present with `margin_rates`.
    pub margin: Option<f64>,
}

fn mat_vec(a: &Matrix, x: &[f64]) -> Vec<f64> {
    a.iter()
        .map(|r| r.iter().zip(x).map(|(p, q)| p * q).sum())
        .collect()
}

fn dot(x: &[f64], y: &[f64]) -> f64 {
    x.iter().zip(y).map(|(p, q)| p * q).sum()
}

/// `r = A x + b`.
fn residual_of(a: &Matrix, b: &[f64], x: &[f64]) -> Vec<f64> {
    mat_vec(a, x).iter().zip(b).map(|(p, q)| p + q).collect()
}

/// `f(x) = sum w_i r_i^2 + ridge |x|^2`, from the residual.
fn objective_of(r: &[f64], w: &[f64], ridge: f64, x: &[f64]) -> f64 {
    r.iter().zip(w).map(|(v, w)| w * v * v).sum::<f64>() + ridge * dot(x, x)
}

/// `H = A^T W A + ridge I` (exactly symmetric) and `c = A^T W b`.
fn normal_equations(a: &Matrix, b: &[f64], w: &[f64], ridge: f64) -> (Matrix, Vec<f64>) {
    let n = a[0].len();
    let mut h = vec![vec![0.0; n]; n];
    let mut c = vec![0.0; n];
    for (row, (bi, wi)) in a.iter().zip(b.iter().zip(w)) {
        for i in 0..n {
            c[i] += row[i] * wi * bi;
            for j in 0..=i {
                h[i][j] += row[i] * wi * row[j];
            }
        }
    }
    for i in 0..n {
        h[i][i] += ridge;
        for j in 0..i {
            h[j][i] = h[i][j];
        }
    }
    (h, c)
}

/// Largest absolute eigenvalue of a symmetric matrix.
fn spectral_scale(eigenvalues: &[f64]) -> f64 {
    eigenvalues.iter().fold(0.0f64, |m, v| m.max(v.abs()))
}

/// Check 1 of `hedge.qp.solve` and `hedge.integer.solve` for `a`, `b`, `weights`: `(m, n)`.
fn check_system(a: &Matrix, b: &[f64], weights: &[f64]) -> Result<(usize, usize)> {
    let m = a.len();
    let n = a.first().map_or(0, Vec::len);
    if m == 0 || n == 0 || a.iter().any(|r| r.len() != n) {
        return fail(
            "E_INPUT",
            "a must be a non-empty matrix with rows of one length",
        );
    }
    if b.len() != m || weights.len() != m {
        return fail("E_INPUT", "b and weights need one entry per row of a");
    }
    Ok((m, n))
}

/// `E^T = Q R` by Householder reflections: returns `(Q, R)`, `Q` `n x n` orthogonal (columns),
/// `R` the leading `k x k` upper triangle.
fn householder_qr(e: &[Vec<f64>], n: usize) -> (Matrix, Matrix) {
    let k = e.len();
    // Work on E^T, n x k.
    let mut m: Matrix = (0..n).map(|i| (0..k).map(|j| e[j][i]).collect()).collect();
    let mut q: Matrix = (0..n)
        .map(|i| (0..n).map(|j| f64::from(u8::from(i == j))).collect())
        .collect();
    for col in 0..k.min(n) {
        let norm = (col..n).map(|i| m[i][col] * m[i][col]).sum::<f64>().sqrt();
        if norm == 0.0 {
            continue;
        }
        let alpha = if m[col][col] > 0.0 { -norm } else { norm };
        let mut v: Vec<f64> = (0..n)
            .map(|i| if i < col { 0.0 } else { m[i][col] })
            .collect();
        v[col] -= alpha;
        let vv = dot(&v, &v);
        if vv == 0.0 {
            continue;
        }
        for j in 0..k {
            let s = 2.0 * (col..n).map(|i| v[i] * m[i][j]).sum::<f64>() / vv;
            for i in col..n {
                m[i][j] -= s * v[i];
            }
        }
        // Q <- Q (I - 2 v v^T / v^T v).
        for row in &mut q {
            let s = 2.0 * (col..n).map(|i| row[i] * v[i]).sum::<f64>() / vv;
            for i in col..n {
                row[i] -= s * v[i];
            }
        }
    }
    let r = (0..k).map(|i| (0..k).map(|j| m[i][j]).collect()).collect();
    (q, r)
}

/// Inverse of a symmetric positive definite matrix, column by column.
fn spd_inverse(g: &Matrix) -> Result<Matrix> {
    let n = g.len();
    let mut inv = vec![vec![0.0; n]; n];
    for j in 0..n {
        let e: Vec<f64> = (0..n).map(|i| f64::from(u8::from(i == j))).collect();
        let col = solve(g, &e)?;
        for i in 0..n {
            inv[i][j] = col[i];
        }
    }
    for i in 0..n {
        for j in 0..i {
            let v = (inv[i][j] + inv[j][i]) / 2.0;
            inv[i][j] = v;
            inv[j][i] = v;
        }
    }
    Ok(inv)
}

/// One inequality `c^T y >= d`, with the scale used for its violation test.
struct Constraint {
    normal: Vec<f64>,
    rhs: f64,
    scale: f64,
}

/// For the active set `N` (columns `normals`): `B = G^{-1} N` and `M^{-1}`, `M = N^T B`.
fn active_factors(
    ginv: &Matrix,
    cons: &[Constraint],
    active: &[usize],
) -> Result<(Matrix, Matrix)> {
    let b: Matrix = active
        .iter()
        .map(|&j| mat_vec(ginv, &cons[j].normal))
        .collect();
    let q = active.len();
    let m: Matrix = (0..q)
        .map(|i| {
            (0..q)
                .map(|j| dot(&cons[active[i]].normal, &b[j]))
                .collect()
        })
        .collect();
    let minv = if q == 0 {
        Vec::new()
    } else {
        general_inverse(&m)?
    };
    Ok((b, minv))
}

fn general_inverse(m: &Matrix) -> Result<Matrix> {
    let q = m.len();
    let mut inv = vec![vec![0.0; q]; q];
    for j in 0..q {
        let e: Vec<f64> = (0..q).map(|i| f64::from(u8::from(i == j))).collect();
        let col = solve(m, &e)?;
        for i in 0..q {
            inv[i][j] = col[i];
        }
    }
    Ok(inv)
}

/// Dual active-set method of Goldfarb and Idnani for `min y^T G y / 2 + lin^T y` subject to
/// `c_i^T y >= d_i`, `G` positive definite. Starts at the unconstrained minimiser and adds the
/// most violated constraint while keeping dual feasibility, so it ends at the unique KKT point
/// or proves that no feasible point exists (`None`). The answer is re-solved on the final
/// active set. Returns `(y, active)`.
fn dual_active_set(
    g: &Matrix,
    lin: &[f64],
    cons: &[Constraint],
    dependence: f64,
) -> Result<Option<(Vec<f64>, Vec<usize>)>> {
    let ginv = spd_inverse(g)?;
    let mut y: Vec<f64> = mat_vec(&ginv, lin).iter().map(|v| -v).collect();
    let mut active: Vec<usize> = Vec::new();
    let mut u: Vec<f64> = Vec::new();
    let limit = 50 * (cons.len() + g.len() + 1);
    for _ in 0..limit {
        let slack = |y: &[f64], j: usize| dot(&cons[j].normal, y) - cons[j].rhs;
        let p = (0..cons.len())
            .filter(|j| !active.contains(j))
            .map(|j| (j, slack(&y, j) / cons[j].scale))
            .filter(|&(_, s)| s < -THRESHOLD)
            .min_by(|x, z| x.1.total_cmp(&z.1))
            .map(|(j, _)| j);
        let Some(p) = p else {
            let (b, minv) = active_factors(&ginv, cons, &active)?;
            // KKT on the active set: lambda = M^{-1} (d + B^T lin), y = B lambda - G^{-1} lin.
            let rhs: Vec<f64> = active
                .iter()
                .enumerate()
                .map(|(i, &j)| cons[j].rhs + dot(&b[i], lin))
                .collect();
            let lambda = mat_vec(&minv, &rhs);
            let mut y = mat_vec(&ginv, lin);
            for v in &mut y {
                *v = -*v;
            }
            for (bi, li) in b.iter().zip(&lambda) {
                for (v, w) in y.iter_mut().zip(bi) {
                    *v += li * w;
                }
            }
            return Ok(Some((y, active)));
        };
        let mut up = 0.0;
        let normal = &cons[p].normal;
        let gn = dot(normal, &mat_vec(&ginv, normal));
        loop {
            let (b, minv) = active_factors(&ginv, cons, &active)?;
            let bt_n: Vec<f64> = b.iter().map(|bi| dot(bi, normal)).collect();
            let r = mat_vec(&minv, &bt_n);
            let mut z = mat_vec(&ginv, normal);
            for (bi, ri) in b.iter().zip(&r) {
                for (v, w) in z.iter_mut().zip(bi) {
                    *v -= ri * w;
                }
            }
            let mut t1 = f64::INFINITY;
            let mut drop = None;
            for (i, ri) in r.iter().enumerate() {
                if *ri > 0.0 && u[i] / ri < t1 {
                    t1 = u[i] / ri;
                    drop = Some(i);
                }
            }
            let zn = dot(&z, normal);
            let t2 = if zn > dependence * gn {
                -(dot(normal, &y) - cons[p].rhs) / zn
            } else {
                f64::INFINITY
            };
            let t = t1.min(t2);
            if t == f64::INFINITY {
                return Ok(None);
            }
            if t2.is_finite() {
                for (v, w) in y.iter_mut().zip(&z) {
                    *v += t * w;
                }
            }
            for (ui, ri) in u.iter_mut().zip(&r) {
                *ui -= t * ri;
            }
            up += t;
            if t2 <= t1 {
                active.push(p);
                u.push(up);
                break;
            }
            let i = drop.expect("t1 is finite");
            active.remove(i);
            u.remove(i);
        }
    }
    fail("E_NO_CONVERGENCE", "active-set iteration limit reached")
}

/// An inequality `normal^T x >= rhs` in the variables of the problem; when it is active at the
/// answer, `snap` sets one variable exactly (a bound, or zero for a sign or split constraint).
struct Ineq {
    normal: Vec<f64>,
    rhs: f64,
    snap: Option<(usize, f64)>,
}

impl Ineq {
    fn unit(n: usize, j: usize, sign: f64, rhs: f64, snap: f64) -> Ineq {
        let mut normal = vec![0.0; n];
        normal[j] = sign;
        Ineq {
            normal,
            rhs,
            snap: Some((j, snap)),
        }
    }
}

/// The bounds as inequalities.
fn bound_rows(lower: &[Option<f64>], upper: &[Option<f64>]) -> Vec<Ineq> {
    let n = lower.len();
    let mut out = Vec::new();
    for j in 0..n {
        if let Some(l) = lower[j] {
            out.push(Ineq::unit(n, j, 1.0, l, l));
        }
        if let Some(u) = upper[j] {
            out.push(Ineq::unit(n, j, -1.0, -u, u));
        }
    }
    out
}

/// `E x = e` with `E` of full row rank: the minimum-norm solution `x_p` and the rows of `Z`, an
/// orthonormal basis of the null space (`Z = I` when there is no equality).
fn null_space(e: &[Vec<f64>], rhs: &[f64], n: usize) -> (Vec<f64>, Matrix) {
    let k = e.len();
    let (q, r) = householder_qr(e, n);
    // x_p = Q_1 w with R^T w = e (forward substitution).
    let mut w = vec![0.0; k];
    for i in 0..k {
        let s: f64 = (0..i).map(|j| r[j][i] * w[j]).sum();
        w[i] = (rhs[i] - s) / r[i][i];
    }
    let xp = (0..n)
        .map(|i| (0..k).map(|j| q[i][j] * w[j]).sum())
        .collect();
    (xp, (0..n).map(|i| q[i][k..].to_vec()).collect())
}

/// The reduced problem `G = Z^T H Z` (exactly symmetric) and `lin = Z^T (H x_p + c)`.
fn reduced(h: &Matrix, c: &[f64], xp: &[f64], z_rows: &Matrix) -> (Matrix, Vec<f64>) {
    let n = h.len();
    let dim = z_rows.first().map_or(0, Vec::len);
    let hz: Matrix = h
        .iter()
        .map(|row| {
            (0..dim)
                .map(|j| (0..n).map(|l| row[l] * z_rows[l][j]).sum())
                .collect()
        })
        .collect();
    let mut g: Matrix = (0..dim)
        .map(|i| {
            (0..dim)
                .map(|j| (0..n).map(|l| z_rows[l][i] * hz[l][j]).sum())
                .collect()
        })
        .collect();
    for i in 0..dim {
        for j in 0..i {
            let v = (g[i][j] + g[j][i]) / 2.0;
            g[i][j] = v;
            g[j][i] = v;
        }
    }
    let hxp: Vec<f64> = mat_vec(h, xp).iter().zip(c).map(|(u, v)| u + v).collect();
    let lin = (0..dim)
        .map(|j| (0..n).map(|l| z_rows[l][j] * hxp[l]).sum())
        .collect();
    (g, lin)
}

/// Minimises `y^T G y + 2 lin^T y` over `x = xp + Z y` subject to `ineqs` (in `x`). Returns
/// `x` with the snaps of the active inequalities applied, or `None` if no point is feasible.
fn minimise(
    g: &Matrix,
    lin: &[f64],
    z_rows: &Matrix,
    xp: &[f64],
    ineqs: &[Ineq],
    dependence: f64,
) -> Result<Option<Vec<f64>>> {
    let dim = g.len();
    let cons: Vec<Constraint> = ineqs
        .iter()
        .map(|q| {
            let normal: Vec<f64> = (0..dim)
                .map(|j| {
                    z_rows
                        .iter()
                        .zip(&q.normal)
                        .map(|(row, a)| a * row[j])
                        .sum()
                })
                .collect();
            let norm = dot(&normal, &normal).sqrt().max(f64::MIN_POSITIVE);
            Constraint {
                rhs: q.rhs - dot(&q.normal, xp),
                scale: norm * q.rhs.abs().max(1.0),
                normal,
            }
        })
        .collect();
    let Some((y, active)) = dual_active_set(g, lin, &cons, dependence)? else {
        return Ok(None);
    };
    let mut x: Vec<f64> = z_rows
        .iter()
        .zip(xp)
        .map(|(row, p)| p + dot(row, &y))
        .collect();
    for i in active {
        if let Some((j, v)) = ineqs[i].snap {
            x[j] = v;
        }
    }
    Ok(Some(x))
}

/// Minimises `y^T G y + 2 lin^T y` with `x = xp + Z y` inside the bounds. Returns `x`, with
/// active bounds set exactly, or `None` if infeasible.
fn bounded_minimiser(
    g: &Matrix,
    lin: &[f64],
    z_rows: &Matrix,
    xp: &[f64],
    lower: &[Option<f64>],
    upper: &[Option<f64>],
) -> Result<Option<Vec<f64>>> {
    minimise(g, lin, z_rows, xp, &bound_rows(lower, upper), THRESHOLD)
}

/// The cost and margin terms of the wave 4a problem: `spread_j = cost_weight half_spreads_j`
/// and the margin row `sum m_j |x_j| <= limit`.
struct Kinks<'a> {
    spread: Vec<f64>,
    margin: Option<(&'a [f64], f64)>,
}

/// The non-smooth wave 4a problem: `x^T H x + 2 c^T x + sum_j spread_j |x_j|` with the
/// equalities, bounds and the optional margin row.
///
/// First the split problem `x = p - n`, `p, n >= 0` (costs and margin are linear there), with a
/// small `delta (|p|^2 + |n|^2)` that makes its Hessian definite, finds the sign state: which
/// `x_j` are zero, positive or negative. Then the exact problem is solved on that orthant
/// (zeros fixed, signs as constraints), where it is smooth, so zeros come out as exactly `0.0`.
/// The orthant holds the minimiser whenever the sign state is not degenerate (spec Q-I2).
fn nonsmooth_minimiser(
    h: &Matrix,
    c: &[f64],
    (e, rhs): (&[Vec<f64>], &[f64]),
    (lower, upper): (&[Option<f64>], &[Option<f64>]),
    k: &Kinks,
) -> Result<Option<Vec<f64>>> {
    let n = h.len();
    let spread = &k.spread;
    let delta = SPLIT_DELTA * spectral_scale(&eigen_symmetric(h)?).max(f64::MIN_POSITIVE);
    let h2: Matrix = (0..2 * n)
        .map(|i| {
            (0..2 * n)
                .map(|j| {
                    let sign = if (i < n) == (j < n) { 1.0 } else { -1.0 };
                    sign * h[i % n][j % n] + if i == j { delta } else { 0.0 }
                })
                .collect()
        })
        .collect();
    let c2: Vec<f64> = (0..2 * n)
        .map(|i| if i < n { c[i] } else { -c[i - n] } + spread[i % n] / 2.0)
        .collect();
    let e2: Matrix = e
        .iter()
        .map(|row| row.iter().copied().chain(row.iter().map(|v| -v)).collect())
        .collect();
    let mut rows2: Vec<Ineq> = (0..2 * n)
        .map(|i| Ineq::unit(2 * n, i, 1.0, 0.0, 0.0))
        .collect();
    for j in 0..n {
        let mut d = vec![0.0; 2 * n];
        (d[j], d[n + j]) = (1.0, -1.0);
        if let Some(l) = lower[j] {
            rows2.push(Ineq {
                normal: d.clone(),
                rhs: l,
                snap: None,
            });
        }
        if let Some(u) = upper[j] {
            rows2.push(Ineq {
                normal: d.iter().map(|v| -v).collect(),
                rhs: -u,
                snap: None,
            });
        }
    }
    if let Some((m, limit)) = k.margin {
        rows2.push(Ineq {
            normal: (0..2 * n).map(|i| -m[i % n]).collect(),
            rhs: -limit,
            snap: None,
        });
    }
    let (xp2, z2) = null_space(&e2, rhs, 2 * n);
    let (g2, lin2) = reduced(&h2, &c2, &xp2, &z2);
    let Some(split) = minimise(&g2, &lin2, &z2, &xp2, &rows2, SPLIT_DEPENDENCE)? else {
        return Ok(None);
    };
    let x0: Vec<f64> = (0..n).map(|j| split[j] - split[n + j]).collect();
    let sign: Vec<f64> = (0..n)
        .map(|j| {
            if split[j] == 0.0 && split[n + j] == 0.0 {
                0.0
            } else if x0[j] >= 0.0 {
                1.0
            } else {
                -1.0
            }
        })
        .collect();
    let c3: Vec<f64> = (0..n).map(|j| c[j] + sign[j] * spread[j] / 2.0).collect();
    let mut rows = bound_rows(lower, upper);
    for (j, s) in sign.iter().enumerate() {
        rows.push(Ineq::unit(n, j, if *s == 0.0 { 1.0 } else { *s }, 0.0, 0.0));
        if *s == 0.0 {
            rows.push(Ineq::unit(n, j, -1.0, 0.0, 0.0));
        }
    }
    if let Some((m, limit)) = k.margin {
        rows.push(Ineq {
            normal: (0..n).map(|j| -m[j] * sign[j]).collect(),
            rhs: -limit,
            snap: None,
        });
    }
    let (xp, z) = null_space(e, rhs, n);
    let (g, lin) = reduced(h, &c3, &xp, &z);
    // The split answer is kept only if the orthant has no feasible point, which a correct sign
    // state rules out; it is within about SPLIT_DELTA of the minimiser.
    Ok(Some(
        minimise(&g, &lin, &z, &xp, &rows, THRESHOLD)?.unwrap_or(x0),
    ))
}

/// The finite rule F-2 on every input of `hedge.qp.solve`.
fn check_finite(p: &QpProblem) -> Result<()> {
    finite("a", &p.a)?;
    finite("b", &p.b)?;
    finite("weights", &p.weights)?;
    finite("ridge", &p.ridge)?;
    finite("eq_matrix", &p.eq_matrix)?;
    finite("eq_rhs", &p.eq_rhs)?;
    finite("lower", &p.lower)?;
    finite("upper", &p.upper)?;
    let c = &p.costs;
    finite("half_spreads", &c.half_spreads)?;
    finite("impact", &c.impact)?;
    finite("cost_weight", &c.cost_weight)?;
    finite("margin_rates", &c.margin_rates)?;
    finite("margin_limit", &c.margin_limit)
}

/// Checks I-25 1 to 3 on the cost inputs (after wave 1 checks 1 to 3).
fn check_costs(c: &Costs, n: usize, min_norm: bool) -> Result<()> {
    let lists = [c.half_spreads, c.impact, c.margin_rates];
    if lists.iter().flatten().any(|v| v.len() != n)
        || c.margin_rates.is_some() != c.margin_limit.is_some()
    {
        return fail(
            "E_INPUT",
            "cost lists need n entries; margin_rates and margin_limit go together",
        );
    }
    if min_norm && c.any() {
        return fail(
            "E_INPUT",
            "MIN_NORM does not take costs or margin (ruling I-25)",
        );
    }
    if lists.iter().flatten().any(|v| v.iter().any(|x| *x < 0.0))
        || c.cost_weight.is_some_and(|w| w < 0.0)
        || c.margin_limit.is_some_and(|l| l < 0.0)
    {
        return fail(
            "E_DOMAIN",
            "costs, cost weight and margin must be non-negative",
        );
    }
    Ok(())
}

/// `hedge.qp.solve`: weighted least squares on the residual `A x + b` with ridge, equalities and
/// bounds (HEDGE-04, HEDGE-05).
///
/// # Errors
/// `E_DOMAIN` for a non-finite input (F-2), then the checks of the spec in order: `E_INPUT`
/// (shapes, `MIN_NORM` with a bound), `E_DOMAIN` (weights, ridge, crossed bounds), `E_SINGULAR`
/// (equality rank, reduced Hessian under `ERROR`), `E_INFEASIBLE`.
pub fn qp_solve(p: &QpProblem) -> Result<QpSolution> {
    check_finite(p)?;
    let (_, n) = check_system(p.a, p.b, p.weights)?;
    let (e, rhs): (&[Vec<f64>], &[f64]) = match (p.eq_matrix, p.eq_rhs) {
        (Some(e), Some(r)) => (e, r),
        (None, None) => (&[], &[]),
        _ => return fail("E_INPUT", "eq_matrix and eq_rhs go together"),
    };
    if e.iter().any(|r| r.len() != n) || rhs.len() != e.len() {
        return fail(
            "E_INPUT",
            "eq_matrix rows need n entries and eq_rhs one per row",
        );
    }
    let none = vec![None; n];
    let lower = p.lower.unwrap_or(&none);
    let upper = p.upper.unwrap_or(&none);
    if lower.len() != n || upper.len() != n {
        return fail("E_INPUT", "lower and upper need one entry per instrument");
    }
    let bounded = lower.iter().chain(upper).any(Option::is_some);
    if p.singular == Singular::MinNorm && bounded {
        return fail("E_INPUT", "MIN_NORM does not take bounds (ruling I-5)");
    }
    if p.weights.iter().any(|w| *w <= 0.0) || p.ridge < 0.0 {
        return fail(
            "E_DOMAIN",
            "weights must be positive and ridge non-negative",
        );
    }
    if lower
        .iter()
        .zip(upper)
        .any(|(l, u)| matches!((l, u), (Some(l), Some(u)) if l > u))
    {
        return fail("E_DOMAIN", "a lower bound is above its upper bound");
    }
    let costs = &p.costs;
    check_costs(costs, n, p.singular == Singular::MinNorm)?;
    let k = e.len();
    if k > n {
        return fail("E_SINGULAR", "more equalities than instruments");
    }
    if k > 0 {
        let et: Matrix = (0..n).map(|i| (0..k).map(|j| e[j][i]).collect()).collect();
        let sv = singular_values(&et);
        let largest = sv.iter().fold(0.0f64, |m, v| m.max(*v));
        if sv.iter().any(|v| *v <= THRESHOLD * largest) {
            return fail("E_SINGULAR", "the equality rows are dependent");
        }
    }
    let (xp, z_rows) = null_space(e, rhs, n);
    let cost_weight = costs.cost_weight.unwrap_or(1.0);
    let zeros = vec![0.0; n];
    let impact = costs.impact.unwrap_or(&zeros);
    let half_spreads = costs.half_spreads.unwrap_or(&zeros);
    // I-26: impact enters the Hessian like a ridge; a spread cost does not.
    let (mut h, c) = normal_equations(p.a, p.b, p.weights, p.ridge);
    for j in 0..n {
        h[j][j] += cost_weight * impact[j];
    }
    let limit = THRESHOLD * spectral_scale(&eigen_symmetric(&h)?);
    let dim = n - k;
    let (g, lin) = reduced(&h, &c, &xp, &z_rows);
    let (values, vectors) = if dim == 0 {
        (Vec::new(), Vec::new())
    } else {
        eigen_pairs(&g)?
    };
    let rank = values.iter().filter(|v| **v > limit).count();
    let margin = costs.margin_rates.zip(costs.margin_limit);
    let kinks = Kinks {
        spread: half_spreads.iter().map(|s| cost_weight * s).collect(),
        margin,
    };
    let nonsmooth = margin.is_some() || kinks.spread.iter().any(|s| *s > 0.0);
    let x = if rank < dim {
        if p.singular == Singular::Error {
            return fail("E_SINGULAR", "the reduced Hessian is singular");
        }
        // y = -(Z^T H Z)^+ lin over the kept eigenpairs.
        let mut y = vec![0.0; dim];
        for (v, vec) in values.iter().zip(&vectors) {
            if *v > limit {
                let s = dot(vec, &lin) / v;
                for (yi, wi) in y.iter_mut().zip(vec) {
                    *yi -= s * wi;
                }
            }
        }
        z_rows
            .iter()
            .zip(&xp)
            .map(|(row, p)| p + dot(row, &y))
            .collect()
    } else if dim == 0 {
        let tol = |v: f64| THRESHOLD * v.abs().max(1.0);
        let outside = xp.iter().zip(lower.iter().zip(upper)).any(|(x, (l, u))| {
            l.is_some_and(|l| *x < l - tol(l)) || u.is_some_and(|u| *x > u + tol(u))
        }) || margin.is_some_and(|(m, l)| {
            m.iter().zip(&xp).map(|(m, x)| m * x.abs()).sum::<f64>() > l + tol(l)
        });
        if outside {
            return fail(
                "E_INFEASIBLE",
                "the equalities leave no point inside the bounds and margin",
            );
        }
        xp
    } else {
        let found = if nonsmooth {
            nonsmooth_minimiser(&h, &c, (e, rhs), (lower, upper), &kinks)?
        } else {
            bounded_minimiser(&g, &lin, &z_rows, &xp, lower, upper)?
        };
        match found {
            Some(x) => x,
            None => return fail("E_INFEASIBLE", "no point satisfies the constraints"),
        }
    };
    let residual = residual_of(p.a, p.b, &x);
    let risk = objective_of(&residual, p.weights, p.ridge, &x);
    let cost: f64 = (0..n)
        .map(|j| half_spreads[j] * x[j].abs() + impact[j] * x[j] * x[j])
        .sum();
    let with_costs = costs.any();
    Ok(QpSolution {
        objective: if with_costs {
            risk + cost_weight * cost
        } else {
            risk
        },
        risk: with_costs.then_some(risk),
        cost: with_costs.then_some(cost),
        margin: costs
            .margin_rates
            .map(|m| m.iter().zip(&x).map(|(m, x)| m * x.abs()).sum()),
        x,
        residual,
        rank,
    })
}

/// One point of `hedge.frontier.solve`.
#[derive(Debug, Clone, PartialEq)]
pub struct FrontierPoint {
    pub cost_weight: f64,
    pub x: Vec<f64>,
    pub risk: f64,
    pub cost: f64,
}

/// `hedge.frontier.solve`: `hedge.qp.solve` once per cost weight, in order; the first error
/// stops it. `p.costs.cost_weight` must be absent.
///
/// # Errors
/// `E_DOMAIN` for a non-finite weight; `E_INPUT` (`cost_weight` given, weights empty or not
/// strictly increasing, no `half_spreads` or `impact`); then the errors of `hedge.qp.solve`.
pub fn frontier_solve(p: &QpProblem, cost_weights: &[f64]) -> Result<Vec<FrontierPoint>> {
    check_finite(p)?;
    finite("cost_weights", &cost_weights)?;
    if p.costs.cost_weight.is_some()
        || cost_weights.is_empty()
        || cost_weights.windows(2).any(|w| w[1] <= w[0])
        || (p.costs.half_spreads.is_none() && p.costs.impact.is_none())
    {
        return fail(
            "E_INPUT",
            "cost_weights strictly increasing, no cost_weight, and a cost to weigh",
        );
    }
    cost_weights
        .iter()
        .map(|w| {
            let mut q = p.clone();
            q.costs.cost_weight = Some(*w);
            let s = qp_solve(&q)?;
            Ok(FrontierPoint {
                cost_weight: *w,
                risk: s.risk.unwrap_or(s.objective),
                cost: s.cost.unwrap_or(0.0),
                x: s.x,
            })
        })
        .collect()
}

/// Inputs of `hedge.integer.solve`. Lot bounds hold `None` for "no bound".
#[derive(Debug, Clone)]
pub struct IntegerProblem<'a> {
    pub a: &'a Matrix,
    pub b: &'a [f64],
    pub weights: &'a [f64],
    pub ridge: f64,
    pub lot_sizes: &'a [f64],
    pub lower_lots: Option<&'a [Option<i64>]>,
    pub upper_lots: Option<&'a [Option<i64>]>,
}

/// Outputs of `hedge.integer.solve`.
#[derive(Debug, Clone, PartialEq)]
pub struct IntegerSolution {
    pub lots: Vec<i64>,
    pub x: Vec<f64>,
    pub residual: Vec<f64>,
    pub objective: f64,
    pub continuous_objective: f64,
    pub rounding_cost: f64,
}

/// The integer search: problem in lot units and the best point so far.
struct LotSearch<'a> {
    g: Matrix,
    lin: Vec<f64>,
    eye: Matrix,
    zero: Vec<f64>,
    a: &'a Matrix,
    b: &'a [f64],
    w: &'a [f64],
    ridge: f64,
    lot_sizes: &'a [f64],
    best: Option<(f64, Vec<i64>)>,
}

impl LotSearch<'_> {
    fn value(&self, lots: &[f64]) -> f64 {
        let x: Vec<f64> = lots
            .iter()
            .zip(self.lot_sizes)
            .map(|(n, s)| n * s)
            .collect();
        objective_of(&residual_of(self.a, self.b, &x), self.w, self.ridge, &x)
    }

    /// Keeps the better of the incumbent and `lots` under ruling I-7.
    fn offer(&mut self, lots: Vec<i64>) {
        #[allow(clippy::cast_precision_loss)]
        let f = self.value(&lots.iter().map(|v| *v as f64).collect::<Vec<_>>());
        let better = match &self.best {
            None => true,
            Some((b, cur)) => {
                if (f - b).abs() <= THRESHOLD * f.max(*b) {
                    let size = |v: &[i64]| v.iter().map(|x| x.unsigned_abs()).sum::<u64>();
                    (size(&lots), &lots) < (size(cur), cur)
                } else {
                    f < *b
                }
            }
        };
        if better {
            self.best = Some((f, lots));
        }
    }

    /// Branch and bound on the box `[lower, upper]`, pruned by the continuous relaxation.
    #[allow(clippy::cast_possible_truncation, clippy::cast_precision_loss)]
    fn branch(&mut self, lower: &mut [Option<f64>], upper: &mut [Option<f64>]) -> Result<()> {
        let Some(y) = bounded_minimiser(&self.g, &self.lin, &self.eye, &self.zero, lower, upper)?
        else {
            return Ok(());
        };
        let bound = self.value(&y);
        if let Some((b, _)) = &self.best
            && bound > b * (1.0 + 1e-9)
        {
            return Ok(());
        }
        let far = y
            .iter()
            .enumerate()
            .map(|(j, v)| (j, (v - v.round()).abs()))
            .filter(|&(_, d)| d > 1e-9)
            .max_by(|p, q| p.1.total_cmp(&q.1));
        let Some((j, _)) = far else {
            self.offer(y.iter().map(|v| v.round() as i64).collect());
            return Ok(());
        };
        let (lo, hi) = (lower[j], upper[j]);
        let down = y[j].floor();
        // The nearer side first, so the incumbent improves early.
        let order = if y[j] - down <= 0.5 {
            [true, false]
        } else {
            [false, true]
        };
        for go_down in order {
            if go_down {
                upper[j] = Some(down);
            } else {
                lower[j] = Some(down + 1.0);
            }
            self.branch(lower, upper)?;
            lower[j] = lo;
            upper[j] = hi;
        }
        Ok(())
    }
}

/// `hedge.integer.solve`: the hedge objective over whole lots, `x_j = lot_sizes_j n_j`.
///
/// # Errors
/// `E_DOMAIN` for a non-finite input, then `E_INPUT` (shapes), `E_DOMAIN` (weights, ridge, lot
/// sizes, crossed lot bounds) and `E_SINGULAR` (the problem in lot units is not strictly convex,
/// ruling I-6).
#[allow(clippy::cast_precision_loss)]
pub fn integer_solve(p: &IntegerProblem) -> Result<IntegerSolution> {
    finite("a", &p.a)?;
    finite("b", &p.b)?;
    finite("weights", &p.weights)?;
    finite("ridge", &p.ridge)?;
    finite("lot_sizes", &p.lot_sizes)?;
    let (_, n) = check_system(p.a, p.b, p.weights)?;
    let none = vec![None; n];
    let lower = p.lower_lots.unwrap_or(&none);
    let upper = p.upper_lots.unwrap_or(&none);
    if p.lot_sizes.len() != n || lower.len() != n || upper.len() != n {
        return fail(
            "E_INPUT",
            "lot_sizes and lot bounds need one entry per instrument",
        );
    }
    if p.weights.iter().any(|w| *w <= 0.0)
        || p.ridge < 0.0
        || p.lot_sizes.iter().any(|s| *s <= 0.0)
        || lower
            .iter()
            .zip(upper)
            .any(|(l, u)| matches!((l, u), (Some(l), Some(u)) if l > u))
    {
        return fail(
            "E_DOMAIN",
            "weights and lot sizes must be positive, ridge non-negative, lot bounds ordered",
        );
    }
    let (h, c) = normal_equations(p.a, p.b, p.weights, p.ridge);
    let s = p.lot_sizes;
    let g: Matrix = (0..n)
        .map(|i| (0..n).map(|j| s[i] * h[i][j] * s[j]).collect())
        .collect();
    let lin: Vec<f64> = (0..n).map(|i| s[i] * c[i]).collect();
    let eig = eigen_symmetric(&g)?;
    if eig[0] <= THRESHOLD * spectral_scale(&eig) {
        return fail(
            "E_SINGULAR",
            "the problem in lot units is not strictly convex (ruling I-6)",
        );
    }
    let mut lo: Vec<Option<f64>> = lower.iter().map(|v| v.map(|v| v as f64)).collect();
    let mut hi: Vec<Option<f64>> = upper.iter().map(|v| v.map(|v| v as f64)).collect();
    let eye: Matrix = (0..n)
        .map(|i| (0..n).map(|j| f64::from(u8::from(i == j))).collect())
        .collect();
    let mut search = LotSearch {
        g,
        lin,
        eye,
        zero: vec![0.0; n],
        a: p.a,
        b: p.b,
        w: p.weights,
        ridge: p.ridge,
        lot_sizes: s,
        best: None,
    };
    let Some(relaxed) =
        bounded_minimiser(&search.g, &search.lin, &search.eye, &search.zero, &lo, &hi)?
    else {
        return fail("E_NO_CONVERGENCE", "a box of integers cannot be empty");
    };
    // I-49: integers beyond 2^52 are not all representable, so the search is not defined.
    if relaxed.iter().any(|v| v.abs() > 4_503_599_627_370_496.0) {
        let mut e = crate::error::err("E_LIMIT", "a relaxed lot count is above 2^52 (I-49)");
        e.field = Some("lot_sizes".to_string());
        return Err(e);
    }
    let continuous_objective = search.value(&relaxed);
    search.branch(&mut lo, &mut hi)?;
    let Some((objective, lots)) = search.best else {
        return fail("E_NO_CONVERGENCE", "the search found no integer point");
    };
    let x: Vec<f64> = lots.iter().zip(s).map(|(n, s)| *n as f64 * s).collect();
    let residual = residual_of(p.a, p.b, &x);
    Ok(IntegerSolution {
        lots,
        x,
        residual,
        objective,
        continuous_objective,
        rounding_cost: objective - continuous_objective,
    })
}

/// The two input forms of `hedge.minvar.ratio`.
#[derive(Debug, Clone, Copy)]
pub enum MinVarInput<'a> {
    /// `(k+1) x (k+1)` covariance, index 0 the exposure.
    Covariance(&'a Matrix),
    /// Exposure changes and `k` hedge series.
    Series(&'a [f64], &'a Matrix),
}

/// Outputs of `hedge.minvar.ratio`.
#[derive(Debug, Clone, PartialEq)]
pub struct MinVar {
    pub hedge: Vec<f64>,
    pub variance_before: f64,
    pub variance_after: f64,
    pub effectiveness: f64,
}

fn check_symmetric(s: &Matrix) -> Result<()> {
    let largest = s.iter().flatten().fold(0.0f64, |m, v| m.max(v.abs()));
    let n = s.len();
    for i in 0..n {
        for j in 0..i {
            if (s[i][j] - s[j][i]).abs() > THRESHOLD * largest {
                return fail("E_INPUT", "covariance is not symmetric");
            }
        }
    }
    Ok(())
}

/// Sample covariance with divisor `T - 1` of the series `[e, h_1 .. h_k]`.
#[allow(clippy::cast_precision_loss)]
fn sample_covariance(series: &[&[f64]]) -> Matrix {
    let t = series[0].len();
    let means: Vec<f64> = series
        .iter()
        .map(|s| s.iter().sum::<f64>() / t as f64)
        .collect();
    let n = series.len();
    let mut out = vec![vec![0.0; n]; n];
    for i in 0..n {
        for j in 0..=i {
            let v = (0..t)
                .map(|k| (series[i][k] - means[i]) * (series[j][k] - means[j]))
                .sum::<f64>()
                / (t - 1) as f64;
            out[i][j] = v;
            out[j][i] = v;
        }
    }
    out
}

/// `hedge.minvar.ratio`: units of each hedge that minimise the hedged variance (ruling I-8).
///
/// # Errors
/// `E_DOMAIN` for a non-finite input, then `E_INPUT` (shapes, symmetry, too few observations),
/// `E_DOMAIN` (zero exposure variance), `E_SINGULAR` (hedge block), `E_NOT_POSITIVE_DEFINITE`.
pub fn minvar_ratio(input: MinVarInput) -> Result<MinVar> {
    let s = match input {
        MinVarInput::Covariance(s) => {
            finite("covariance", &s)?;
            let n = s.len();
            if n < 2 || s.iter().any(|r| r.len() != n) {
                return fail("E_INPUT", "covariance must be square and at least 2 x 2");
            }
            check_symmetric(s)?;
            s.clone()
        }
        MinVarInput::Series(e, h) => {
            finite("exposure_changes", &e)?;
            finite("hedge_changes", &h)?;
            let k = h.len();
            if k < 1 || h.iter().any(|v| v.len() != e.len()) {
                return fail(
                    "E_INPUT",
                    "need at least one hedge series, all of one length",
                );
            }
            if e.len() < k + 2 {
                return fail("E_INPUT", "need at least k + 2 observations (ruling I-8)");
            }
            let mut all: Vec<&[f64]> = vec![e];
            all.extend(h.iter().map(Vec::as_slice));
            sample_covariance(&all)
        }
    };
    if s[0][0] <= 0.0 {
        return fail("E_DOMAIN", "the exposure has no variance");
    }
    let k = s.len() - 1;
    // Cholesky of S_hh without pivoting; a pivot at or below the threshold is singular.
    let scale = (1..=k).fold(0.0f64, |m, i| m.max(s[i][i]));
    let mut l = vec![vec![0.0; k]; k];
    for i in 0..k {
        for j in 0..=i {
            let v = s[i + 1][j + 1] - (0..j).map(|q| l[i][q] * l[j][q]).sum::<f64>();
            if i == j {
                if v <= THRESHOLD * scale {
                    return fail("E_SINGULAR", "the hedge instruments are not independent");
                }
                l[i][i] = v.sqrt();
            } else {
                l[i][j] = v / l[j][j];
            }
        }
    }
    // hedge = -S_hh^{-1} S_he by two triangular solves.
    let mut y = vec![0.0; k];
    for i in 0..k {
        y[i] = (s[i + 1][0] - (0..i).map(|q| l[i][q] * y[q]).sum::<f64>()) / l[i][i];
    }
    let mut hedge = vec![0.0; k];
    for i in (0..k).rev() {
        hedge[i] = (y[i] - (i + 1..k).map(|q| l[q][i] * hedge[q]).sum::<f64>()) / l[i][i];
    }
    for v in &mut hedge {
        *v = -*v;
    }
    let variance_before = s[0][0];
    let variance_after = variance_before + (0..k).map(|i| s[i + 1][0] * hedge[i]).sum::<f64>();
    // I-44: below -1e-12 S_00 the matrix is not positive semi-definite; between that and 0 the
    // value is rounding of a perfect hedge, returned as 0.
    if variance_after < -1e-12 * variance_before {
        return fail("E_NOT_POSITIVE_DEFINITE", "the hedged variance is negative");
    }
    let variance_after = variance_after.max(0.0);
    Ok(MinVar {
        hedge,
        variance_before,
        variance_after,
        effectiveness: 1.0 - variance_after / variance_before,
    })
}

/// An instrument of `hedge.greeks.neutralise`.
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum GreekInstrument {
    Underlying,
    /// `call`, `strike`, `expiry_years`.
    Option {
        call: bool,
        strike: f64,
        expiry: f64,
    },
}

/// A Greek that a hedge can target.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Greek {
    Delta,
    Gamma,
    Vega,
}

/// The flat Black-Scholes-Merton market of `hedge.greeks.neutralise`.
#[derive(Debug, Clone, Copy)]
pub struct GreekMarket {
    pub spot: f64,
    pub rate: f64,
    pub dividend_yield: f64,
    pub volatility: f64,
}

/// Outputs of `hedge.greeks.neutralise`; Greeks as `[delta, gamma, vega]`.
#[derive(Debug, Clone, PartialEq)]
pub struct GreekHedge {
    pub quantities: Vec<f64>,
    pub before: [f64; 3],
    pub after: [f64; 3],
}

/// `[delta, gamma, vega]` per unit, vega per unit of volatility (ruling I-9).
/// unchecked: caller guarantees finite inputs with positive spot, volatility, strike and expiry.
#[must_use]
pub fn unit_greeks(m: &GreekMarket, inst: &GreekInstrument) -> [f64; 3] {
    match *inst {
        GreekInstrument::Underlying => [1.0, 0.0, 0.0],
        GreekInstrument::Option {
            call,
            strike,
            expiry,
        } => {
            let sq = expiry.sqrt();
            let vs = m.volatility * sq;
            let d1 = ((m.spot / strike).ln()
                + (m.rate - m.dividend_yield + m.volatility * m.volatility / 2.0) * expiry)
                / vs;
            let carry = (-m.dividend_yield * expiry).exp();
            let delta = if call {
                carry * normal_cdf(d1)
            } else {
                -carry * normal_cdf(-d1)
            };
            let density = normal_pdf(d1);
            [
                delta,
                carry * density / (m.spot * vs),
                m.spot * carry * density * sq,
            ]
        }
    }
}

const fn greek_index(g: Greek) -> usize {
    match g {
        Greek::Delta => 0,
        Greek::Gamma => 1,
        Greek::Vega => 2,
    }
}

fn check_instrument(inst: &GreekInstrument) -> Result<()> {
    match *inst {
        GreekInstrument::Underlying => Ok(()),
        GreekInstrument::Option { strike, expiry, .. } => {
            if strike <= 0.0 || expiry <= 0.0 {
                fail("E_DOMAIN", "strike and expiry_years must be positive")
            } else {
                Ok(())
            }
        }
    }
}

/// The instrument kind of a `hedge.greeks.neutralise` position.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LegKind {
    Call,
    Put,
    Underlying,
}

/// A position or hedge as given: the keys `strike` and `expiry_years` may be absent.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Leg {
    pub kind: LegKind,
    pub strike: Option<f64>,
    pub expiry: Option<f64>,
    /// A key outside the fixed set was given, or a position's `quantity` is missing (I-41).
    pub stray_keys: bool,
}

impl Leg {
    /// Check 1: an underlying has neither key, an option has both.
    fn instrument(&self) -> Result<GreekInstrument> {
        if self.stray_keys {
            return fail(
                "E_INPUT",
                "an instrument has keys outside its fixed set (I-41)",
            );
        }
        match (self.kind, self.strike, self.expiry) {
            (LegKind::Underlying, None, None) => Ok(GreekInstrument::Underlying),
            (LegKind::Call | LegKind::Put, Some(strike), Some(expiry)) => {
                Ok(GreekInstrument::Option {
                    call: self.kind == LegKind::Call,
                    strike,
                    expiry,
                })
            }
            (LegKind::Underlying, ..) => {
                fail("E_INPUT", "the underlying has no strike or expiry_years")
            }
            _ => fail("E_INPUT", "an option needs strike and expiry_years"),
        }
    }
}

/// `hedge.greeks.neutralise`: quantities of the hedges that zero the targeted Greeks.
///
/// # Errors
/// `E_DOMAIN` for a non-finite input, `E_INPUT` (instrument keys, no hedges, target count,
/// repeated target), `E_DOMAIN` (spot, volatility, strike, expiry), `E_SINGULAR` (the Greek
/// matrix).
pub fn greeks_neutralise(
    market: &GreekMarket,
    portfolio: &[(Leg, f64)],
    hedges: &[Leg],
    targets: &[Greek],
) -> Result<GreekHedge> {
    finite("spot", &market.spot)?;
    finite("rate", &market.rate)?;
    finite("dividend_yield", &market.dividend_yield)?;
    finite("volatility", &market.volatility)?;
    for (leg, q) in portfolio {
        finite("portfolio", &[leg.strike, leg.expiry, Some(*q)])?;
    }
    for leg in hedges {
        finite("hedges", &[leg.strike, leg.expiry])?;
    }
    let book: Vec<(GreekInstrument, f64)> = portfolio
        .iter()
        .map(|(leg, q)| Ok((leg.instrument()?, *q)))
        .collect::<Result<_>>()?;
    let hedges: Vec<GreekInstrument> = hedges.iter().map(Leg::instrument).collect::<Result<_>>()?;
    if hedges.is_empty() || targets.len() != hedges.len() {
        return fail("E_INPUT", "need as many targets as hedges, at least one");
    }
    if (1..targets.len()).any(|i| targets[..i].contains(&targets[i])) {
        return fail("E_INPUT", "a target is repeated");
    }
    if market.spot <= 0.0 || market.volatility <= 0.0 {
        return fail("E_DOMAIN", "spot and volatility must be positive");
    }
    for inst in book.iter().map(|p| &p.0).chain(&hedges) {
        check_instrument(inst)?;
    }
    let mut before = [0.0; 3];
    for (inst, q) in &book {
        let g = unit_greeks(market, inst);
        for k in 0..3 {
            before[k] += q * g[k];
        }
    }
    let per_hedge: Vec<[f64; 3]> = hedges.iter().map(|h| unit_greeks(market, h)).collect();
    let g: Matrix = targets
        .iter()
        .map(|t| per_hedge.iter().map(|h| h[greek_index(*t)]).collect())
        .collect();
    let sv = singular_values(&g);
    let largest = sv.iter().fold(0.0f64, |m, v| m.max(*v));
    if sv.iter().any(|v| *v <= THRESHOLD * largest) {
        return fail(
            "E_SINGULAR",
            "the hedges cannot set the targets independently",
        );
    }
    let rhs: Vec<f64> = targets.iter().map(|t| -before[greek_index(*t)]).collect();
    let quantities = solve(&g, &rhs)?;
    let mut after = before;
    for (h, q) in per_hedge.iter().zip(&quantities) {
        for k in 0..3 {
            after[k] += q * h[k];
        }
    }
    Ok(GreekHedge {
        quantities,
        before,
        after,
    })
}

/// Outputs of `hedge.beta.futures`.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct BetaHedge {
    pub contracts: f64,
    pub contracts_held: f64,
    pub beta_after: f64,
}

/// `hedge.beta.futures`: index futures that move a portfolio's beta to a target. `round` rounds
/// half away from zero (ruling I-10); otherwise the exact contract count is held.
///
/// # Errors
/// `E_DOMAIN` for a non-finite input or a value, futures price or multiplier at or below zero.
pub fn beta_futures(
    value: f64,
    beta: f64,
    target: f64,
    futures_price: f64,
    multiplier: f64,
    round: bool,
) -> Result<BetaHedge> {
    finite("inputs", &[value, beta, target, futures_price, multiplier])?;
    if value <= 0.0 || futures_price <= 0.0 || multiplier <= 0.0 {
        return fail(
            "E_DOMAIN",
            "portfolio value, futures price and multiplier must be positive",
        );
    }
    let contracts = (target - beta) * value / (futures_price * multiplier);
    let contracts_held = if round { contracts.round() } else { contracts };
    Ok(BetaHedge {
        contracts,
        contracts_held,
        beta_after: beta + contracts_held * futures_price * multiplier / value,
    })
}

/// Outputs of `hedge.residual.report`.
#[derive(Debug, Clone, PartialEq)]
pub struct ResidualReport {
    pub residual: Vec<f64>,
    pub variance_before: f64,
    pub variance_after: f64,
    pub volatility_after: f64,
    pub effectiveness: f64,
    /// `r_i (S r)_i`, summing to `variance_after` (ruling I-11).
    pub contributions: Vec<f64>,
}

/// `hedge.residual.report`: residual risk of a hedge under a factor covariance.
///
/// # Errors
/// `E_DOMAIN` for a non-finite input, `E_INPUT` (shapes, symmetry), `E_NOT_POSITIVE_DEFINITE`
/// (a negative eigenvalue beyond the threshold), `E_DOMAIN` (nothing to hedge).
pub fn residual_report(a: &Matrix, b: &[f64], x: &[f64], s: &Matrix) -> Result<ResidualReport> {
    finite("a", &a)?;
    finite("b", &b)?;
    finite("x", &x)?;
    finite("covariance", &s)?;
    let m = a.len();
    let n = x.len();
    if m == 0
        || n == 0
        || a.iter().any(|r| r.len() != n)
        || b.len() != m
        || s.len() != m
        || s.iter().any(|r| r.len() != m)
    {
        return fail(
            "E_INPUT",
            "a is m x n, b has m entries, x has n, covariance is m x m",
        );
    }
    check_symmetric(s)?;
    let eig = eigen_symmetric(s)?;
    if eig[0] < -THRESHOLD * spectral_scale(&eig) {
        return fail(
            "E_NOT_POSITIVE_DEFINITE",
            "the covariance has a negative eigenvalue",
        );
    }
    let variance_before = dot(b, &mat_vec(s, b));
    if variance_before <= 0.0 {
        return fail("E_DOMAIN", "the unhedged position has no variance");
    }
    let residual = residual_of(a, b, x);
    let sr = mat_vec(s, &residual);
    let contributions: Vec<f64> = residual.iter().zip(&sr).map(|(r, v)| r * v).collect();
    let variance_after = dot(&residual, &sr);
    Ok(ResidualReport {
        variance_before,
        variance_after,
        volatility_after: variance_after.max(0.0).sqrt(),
        effectiveness: 1.0 - variance_after / variance_before,
        contributions,
        residual,
    })
}

/// Outputs of `hedge.select.solve`.
#[derive(Debug, Clone, PartialEq)]
pub struct Selection {
    /// Chosen 0-based indices, ascending.
    pub selected: Vec<usize>,
    pub x: Vec<f64>,
    pub residual: Vec<f64>,
    pub objective: f64,
}

/// The next `k`-subset of `0..n` in lexicographic order, in place; `false` after the last.
fn next_subset(s: &mut [usize], n: usize) -> bool {
    let k = s.len();
    for i in (0..k).rev() {
        if s[i] < n - k + i {
            s[i] += 1;
            for j in i + 1..k {
                s[j] = s[j - 1] + 1;
            }
            return true;
        }
    }
    false
}

/// `hedge.select.solve`: the best hedge with at most `max_instruments` of the instruments
/// (ruling I-34), by `hedge.qp.solve` on every subset of size 1 to `K`. `p` carries no
/// equalities, singular policy or costs; `extra_keys` says that the input named one of
/// `eq_matrix`, `eq_rhs` or `singular` (I-33).
///
/// # Errors
/// `E_DOMAIN` for a non-finite input; `hedge.qp.solve` checks 1 to 3; `E_INPUT` (`K` outside
/// `1..n`, an extra key); `E_DOMAIN` (a bound that excludes 0); `E_SINGULAR` (the full
/// problem).
pub fn select_solve(p: &QpProblem, max_instruments: i64, extra_keys: bool) -> Result<Selection> {
    check_finite(p)?;
    let (_, n) = check_system(p.a, p.b, p.weights)?;
    let none = vec![None; n];
    let lower = p.lower.unwrap_or(&none);
    let upper = p.upper.unwrap_or(&none);
    if lower.len() != n || upper.len() != n {
        return fail("E_INPUT", "lower and upper need one entry per instrument");
    }
    if p.weights.iter().any(|w| *w <= 0.0)
        || p.ridge < 0.0
        || lower
            .iter()
            .zip(upper)
            .any(|(l, u)| matches!((l, u), (Some(l), Some(u)) if l > u))
    {
        return fail(
            "E_DOMAIN",
            "weights positive, ridge non-negative, bounds ordered",
        );
    }
    let k = usize::try_from(max_instruments).unwrap_or(0);
    if k < 1 || k > n || extra_keys {
        return fail(
            "E_INPUT",
            "max_instruments in 1..n; no equalities or singular policy (ruling I-33)",
        );
    }
    if lower.iter().any(|l| l.is_some_and(|l| l > 0.0))
        || upper.iter().any(|u| u.is_some_and(|u| u < 0.0))
    {
        return fail("E_DOMAIN", "every bound must admit 0 (ruling I-33)");
    }
    let (h, _) = normal_equations(p.a, p.b, p.weights, p.ridge);
    let eig = eigen_symmetric(&h)?;
    if eig[0] <= THRESHOLD * spectral_scale(&eig) {
        return fail("E_SINGULAR", "the full problem is singular");
    }
    let mut best: Option<(f64, Vec<usize>, Vec<f64>)> = None;
    for size in 1..=k {
        let mut s: Vec<usize> = (0..size).collect();
        loop {
            let a: Matrix =
                p.a.iter()
                    .map(|r| s.iter().map(|&j| r[j]).collect())
                    .collect();
            let lo: Vec<Option<f64>> = s.iter().map(|&j| lower[j]).collect();
            let hi: Vec<Option<f64>> = s.iter().map(|&j| upper[j]).collect();
            let sol = qp_solve(&QpProblem {
                a: &a,
                lower: Some(&lo),
                upper: Some(&hi),
                costs: Costs::default(),
                ..p.clone()
            })?;
            // Earlier subsets are smaller or lexicographically smaller, so a later one wins
            // only if it is better beyond the tie margin.
            if best
                .as_ref()
                .is_none_or(|b| sol.objective < b.0 - THRESHOLD * b.0.abs())
            {
                best = Some((sol.objective, s.clone(), sol.x));
            }
            if !next_subset(&mut s, n) {
                break;
            }
        }
    }
    let Some((objective, selected, xs)) = best else {
        return fail("E_NO_CONVERGENCE", "no subset was solved");
    };
    let mut x = vec![0.0; n];
    for (j, v) in selected.iter().zip(xs) {
        x[*j] = v;
    }
    let residual = residual_of(p.a, p.b, &x);
    Ok(Selection {
        selected,
        x,
        residual,
        objective,
    })
}
