# Calibration and parameter estimation

Stage B spec: `least-squares.md`. MLE and Bayesian estimation come in later stages.

## Purpose
Define the scope and shared contract for the calibration and parameter estimation domain.

## Capabilities
- Objective functions, residual scaling and weighting
- Least squares, nonlinear least squares and robust losses
- Gauss-Newton, Levenberg-Marquardt, BFGS and bounded optimisation
- Regularisation, constraints, parameter transforms and initialisation
- Calibration for curves, volatility, stochastic models and credit
- Convergence diagnostics, parameter stability and sensitivity analysis

## Required specification sections
- Mathematical definitions and assumptions
- Inputs, outputs, units and conventions
- Algorithms and numerical considerations
- Error handling and diagnostics
- Data provenance and model versioning
- Validation strategy and independent references
- Performance expectations and benchmark workload
- Limitations and unsupported cases

## Suggested exercises
- Fit a known synthetic parameter set
- Ill-conditioned and underdetermined calibration
- Bounds and infeasible constraints
- Starting-point sensitivity and convergence reporting
- Residual diagnostics and outlier weighting

## Acceptance criteria
- [ ] Domain contract reviewed and versioned.
- [ ] Analytical/simple benchmark cases independently checked.
- [ ] Normal, boundary, invalid and stress inputs covered.
- [ ] All four implementations conform, and the named oracle passes.
- [ ] Numerical diagnostics and failure modes are explicit.
- [ ] Deterministic fixtures and provenance are recorded.
- [ ] Performance baseline exists where relevant.
- [ ] User and developer documentation includes examples and limitations.
