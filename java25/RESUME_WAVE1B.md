# Java resume note: wave 1b (Q4), 2026-11-09 22:20

Branch stage-f-lang-java, worktree C:\Work\Claude\qf-wt\java. Stage-f 6ce9e9a is merged.
Done: phase 0 and wave 1a. Conformance 12,182/12,182 before the merge; joint_f is 13 not implemented. mvn package 293/293.
Q4 is NOT started: no Java code yet.

Resume plan:
1. Read specifications/02-curves/joint-solve-and-funding.md and the instrument specs it names; rulings F-24 to F-27.
2. New class curves/JointSolver: unknowns per F-24 (ln D pillars, OIS_STEPS base and step rates, ln turn factors).
   Solve curve by curve (block lower triangular, F-25), using Newton per block. Build the Jacobian -(dR/dx)^-1 dR/dq
   with a block forward substitution, so cross-block zeros stay exact zeros.
3. Reuse Ois/Projection/Xccy/StepCurve legs for the model rates; for futures, the model rate is the simple rate on
   ACT/360 and the price column uses 0.01 e^{-z} (F-27).
4. CLI in OpsRatesCurves: rates.curve.joint_solve and rates.funding.curve; register them through the Registry.
5. Tests: exact zeros, turn_sensitivity exactly 0 off the turn, and Jacobian against finite differences.
