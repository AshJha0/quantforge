package org.quantforge.curves;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.quantforge.core.Conventions;
import org.quantforge.core.Finite;
import org.quantforge.core.LinearAlgebra;
import org.quantforge.core.QfError;

/**
 * The joint multi-curve solve with calibrated turns, futures-fitted steps and the IFT Jacobian
 * (joint-solve-and-funding.md, rulings F-24 to F-27). Curves are solved block by block in dependency order; the
 * Jacobian is formed by block forward substitution, so an earlier curve's unknowns against a later curve's quotes are
 * exact zeros.
 */
public final class JointSolver {
    private JointSolver() {}

    public enum CurveType { OIS, OIS_STEPS, PROJECTION, XCCY }

    public enum InstrumentType { OIS, FUTURE, DEPOSIT, FRA, SWAP, XCCY }

    /** A curve as given. Fields a type does not use are null. */
    public record CurveSpec(String name, CurveType type, String convention, Curve.Interpolation interpolation,
                            Curve.Shape shape, Jumps jumps, LocalDate[] turns, LocalDate[] stepDates, String index,
                            String discount, String domestic, String foreignProjection, String domesticConvention,
                            String foreignConvention, LocalDate start) {}

    /** An instrument as given; {@code quote} is the rate, spread or price. */
    public record InstrumentSpec(String id, String curve, InstrumentType type, boolean turn, double quote,
                                 String tenor, Long months, LocalDate start, LocalDate end, Double sigma,
                                 Double meanReversion) {}

    public record SolvedCurve(String name, LocalDate[] pillars, double[] discountFactors, Double baseRate,
                              double[] stepRates) {}

    public record TurnFactor(String curve, LocalDate date, double factor) {}

    public record Result(List<SolvedCurve> curves, List<TurnFactor> turnFactors, List<String> unknowns,
                         List<String> quotes, double[][] jacobian, double[][] turnSensitivity,
                         double maxRepricingError) {}

    /** A model: reads the built curves and returns the model value minus the quote. */
    private interface Model {
        double residual(Discounting[] built);
    }

    private static final class Block {
        CurveSpec spec;
        LocalDate asOf;
        int index;
        Conventions.RateIndex convention;
        LocalDate[] pillars = new LocalDate[0];
        LocalDate[] turns = new LocalDate[0];
        int offset;       // first unknown in the global vector
        int size;         // unknowns of this curve
        int[] instruments; // global instrument indices, in instrument order
        Model[] models;
        LocalDate[][] spans; // per instrument: earliest and latest date it reads
        double[] dRdq;     // per instrument, at the solution

        Discounting build(double[] x) {
            int nTurn = turns.length;
            int nMain = size - nTurn;
            Jumps j = merged(spec.jumps(), turns, Arrays.copyOfRange(x, offset + nMain, offset + size));
            if (spec.type() == CurveType.OIS_STEPS) {
                return StepCurve.unchecked(asOf, x[offset],
                        spec.stepDates(), Arrays.copyOfRange(x, offset + 1, offset + nMain), j);
            }
            return Curve.fromLogs(asOf, spec.interpolation(), pillars,
                    Arrays.copyOfRange(x, offset, offset + nMain), j, spec.shape());
        }
    }


    // ---- input checks and setup ----

    public static Result solve(LocalDate asOf, List<CurveSpec> curves, List<InstrumentSpec> instruments) {
        Map<String, Integer> names = new HashMap<>();
        Block[] blocks = new Block[curves.size()];
        for (int i = 0; i < curves.size(); i++) {
            CurveSpec c = curves.get(i);
            if (names.containsKey(c.name())) {
                throw new QfError("E_INPUT", "duplicate curve name " + c.name(), "curves");
            }
            for (String ref : new String[] {c.discount(), c.domestic(), c.foreignProjection()}) {
                if (ref == null) {
                    continue;
                }
                Integer k = names.get(ref);
                if (k == null) {
                    throw new QfError("E_INPUT", "curve " + c.name() + " names an unknown or later curve " + ref,
                            "curves");
                }
                CurveType t = curves.get(k).type();
                if (t != CurveType.OIS && t != CurveType.OIS_STEPS) {
                    throw new QfError("E_INPUT", "curve " + c.name() + " must name an OIS curve", "curves");
                }
            }
            names.put(c.name(), i);
            Block b = new Block();
            b.spec = c;
            b.index = i;
            b.asOf = asOf;
            blocks[i] = b;
        }
        Set<String> ids = new HashSet<>();
        List<List<Integer>> perCurve = new ArrayList<>();
        for (int i = 0; i < blocks.length; i++) {
            perCurve.add(new ArrayList<>());
        }
        for (int j = 0; j < instruments.size(); j++) {
            InstrumentSpec s = instruments.get(j);
            if (!ids.add(s.id())) {
                throw new QfError("E_INPUT", "duplicate instrument id " + s.id(), "instruments");
            }
            Integer k = names.get(s.curve());
            if (k == null) {
                throw new QfError("E_INPUT", "instrument " + s.id() + " names an unknown curve", "instruments");
            }
            if (!allowed(curves.get(k).type(), s.type())) {
                throw new QfError("E_INPUT", "instrument type " + s.type() + " not allowed on " + s.curve(),
                        "instruments");
            }
            perCurve.get(k).add(j);
        }
        for (Block b : blocks) {
            CurveSpec c = b.spec;
            if (c.stepDates() != null) {
                StepCurve.checkSteps(asOf, c.stepDates());
            }
            LocalDate[] turns = c.turns() == null ? new LocalDate[0] : c.turns();
            LocalDate previous = asOf;
            for (LocalDate d : turns) {
                if (!d.isAfter(previous)) {
                    throw new QfError("E_INPUT", "turn dates must increase from as_of", "turns");
                }
                previous = d;
            }
            b.turns = turns;
            c.jumps().check(asOf);
        }
        // count rules
        for (Block b : blocks) {
            List<Integer> list = perCurve.get(b.index);
            long turnInstruments = list.stream().filter(j -> instruments.get(j).turn()).count();
            if (turnInstruments != b.turns.length) {
                throw new QfError("E_INPUT", "curve " + b.spec.name() + " needs one turn instrument per turn",
                        "instruments");
            }
            if (b.spec.type() == CurveType.OIS_STEPS) {
                if (list.size() != 1 + b.spec.stepDates().length + b.turns.length) {
                    throw new QfError("E_INPUT", "OIS_STEPS needs 1 + steps + turns instruments", "instruments");
                }
            } else if (list.size() - turnInstruments < 1) {
                throw new QfError("E_INPUT", "curve " + b.spec.name() + " has no pillar instrument", "instruments");
            }
            b.instruments = list.stream().mapToInt(Integer::intValue).toArray();
        }
        // conventions and instrument models, pillars
        int offset = 0;
        for (Block b : blocks) {
            setup(b, asOf, blocks, names, instruments);
            b.offset = offset;
            b.size = b.spec.type() == CurveType.OIS_STEPS ? 1 + b.spec.stepDates().length + b.turns.length
                    : b.pillars.length + b.turns.length;
            if (b.size != b.instruments.length) {
                throw new QfError("E_INPUT", "system is not square", "instruments");
            }
            offset += b.size;
        }
        return run(asOf, blocks, instruments, offset);
    }

    private static boolean allowed(CurveType c, InstrumentType i) {
        return switch (c) {
            case OIS, OIS_STEPS -> i == InstrumentType.OIS || i == InstrumentType.FUTURE;
            case PROJECTION -> i == InstrumentType.DEPOSIT || i == InstrumentType.FRA || i == InstrumentType.SWAP;
            case XCCY -> i == InstrumentType.XCCY;
        };
    }

    private static Jumps merged(Jumps fixed, LocalDate[] turns, double[] lnFactors) {
        int n = fixed.dates().length + turns.length;
        if (turns.length == 0) {
            return fixed;
        }
        LocalDate[] d = new LocalDate[n];
        double[] f = new double[n];
        Integer[] order = new Integer[n];
        for (int i = 0; i < n; i++) {
            order[i] = i;
        }
        int m = fixed.dates().length;
        Arrays.sort(order, (a, b) -> (a < m ? fixed.dates()[a] : turns[a - m])
                .compareTo(b < m ? fixed.dates()[b] : turns[b - m]));
        for (int i = 0; i < n; i++) {
            int k = order[i];
            d[i] = k < m ? fixed.dates()[k] : turns[k - m];
            f[i] = k < m ? fixed.factors()[k] : Math.exp(lnFactors[k - m]);
        }
        return new Jumps(d, f);
    }

    private static void setup(Block b, LocalDate asOf, Block[] blocks, Map<String, Integer> names,
                              List<InstrumentSpec> instruments) {
        CurveSpec c = b.spec;
        int n = b.instruments.length;
        b.models = new Model[n];
        b.spans = new LocalDate[n][];
        b.dRdq = new double[n];
        List<LocalDate> pillars = new ArrayList<>();
        int self = b.index;
        switch (c.type()) {
            case OIS, OIS_STEPS -> {
                b.convention = Conventions.requireOvernight(c.convention());
                for (int k = 0; k < n; k++) {
                    InstrumentSpec s = instruments.get(b.instruments[k]);
                    LocalDate last;
                    if (s.type() == InstrumentType.OIS) {
                        Ois.Legs legs = Ois.legs(b.convention, asOf, s.tenor());
                        double q = s.quote();
                        b.models[k] = built -> legs.parRate(built[self]) - q;
                        b.dRdq[k] = -1.0;
                        last = legs.periods().getLast().payment();
                        b.spans[k] = new LocalDate[] {legs.periods().getFirst().start(), last};
                    } else {
                        if (!s.end().isAfter(s.start())) {
                            throw new QfError("E_INPUT", "future end must be after start", "instruments");
                        }
                        if (s.start().isBefore(asOf)) {
                            throw new QfError("E_DOMAIN", "future start is before as_of", "instruments");
                        }
                        RatesCurves.Convexity cx = RatesCurves.convexity(s.quote(),
                                ChronoUnit.DAYS.between(asOf, s.start()) / 365.0,
                                ChronoUnit.DAYS.between(asOf, s.end()) / 365.0, s.sigma(), s.meanReversion());
                        double alpha = ChronoUnit.DAYS.between(s.start(), s.end()) / 360.0;
                        double target = cx.forwardRate();
                        LocalDate st = s.start();
                        LocalDate en = s.end();
                        b.models[k] = built -> (built[self].discount(st) / built[self].discount(en) - 1.0) / alpha
                                - target;
                        double ez = 1.0 - cx.convexity() / (cx.futuresRate() + 1.0 / (
                                (ChronoUnit.DAYS.between(asOf, en) - ChronoUnit.DAYS.between(asOf, st)) / 365.0));
                        b.dRdq[k] = 0.01 * ez;
                        last = en;
                        b.spans[k] = new LocalDate[] {st, en};
                    }
                    if (!s.turn()) {
                        pillars.add(last);
                    }
                }
            }
            case PROJECTION -> {
                Conventions.RateIndex ix = Conventions.term(c.index());
                int disc = names.get(c.discount());
                LocalDate spot = Projection.spot(ix, asOf);
                for (int k = 0; k < n; k++) {
                    InstrumentSpec s = instruments.get(b.instruments[k]);
                    double q = s.quote();
                    long months = s.months();
                    long least = s.type() == InstrumentType.FRA ? 0 : 1;
                    if (months < least || months > 1200) {
                        throw new QfError("E_INPUT", "months out of range", "instruments");
                    }
                    LocalDate last;
                    if (s.type() == InstrumentType.SWAP) {
                        Projection.Swap sw = Projection.swap(ix, asOf, months);
                        b.models[k] = built -> sw.parRate(built[disc], built[self]) - q;
                        last = sw.fixed().getLast().end();
                        b.spans[k] = new LocalDate[] {spot, last};
                    } else {
                        boolean deposit = s.type() == InstrumentType.DEPOSIT;
                        LocalDate start = deposit ? spot : Projection.plusMonths(ix, spot, months);
                        LocalDate end = Projection.plusMonths(ix, start, deposit ? months : ix.months());
                        b.models[k] = built -> Projection.forward(ix, built[self], start, end) - q;
                        last = end;
                        b.spans[k] = new LocalDate[] {start, end};
                    }
                    b.dRdq[k] = -1.0;
                    if (!s.turn()) {
                        pillars.add(last);
                    }
                }
            }
            case XCCY -> {
                Xccy.checkConventions(Conventions.overnight(c.domesticConvention()),
                        Conventions.overnight(c.foreignConvention()));
                if (c.start().isBefore(asOf)) {
                    throw new QfError("E_OUT_OF_RANGE", "start is before as_of", "start");
                }
                int fp = names.get(c.foreignProjection());
                for (int k = 0; k < n; k++) {
                    InstrumentSpec s = instruments.get(b.instruments[k]);
                    List<LocalDate> dates = Xccy.schedule(c.start(), s.months());
                    double m = s.quote();
                    b.models[k] = built -> Xccy.leg(dates, built[fp], built[self], m);
                    b.dRdq[k] = Double.NaN; // set at the solution: sum alpha_i D_f(e_i)
                    b.spans[k] = new LocalDate[] {dates.getFirst(), dates.getLast()};
                    if (!s.turn()) {
                        pillars.add(dates.getLast());
                    }
                }
            }
        }
        if (c.type() != CurveType.OIS_STEPS) {
            for (int k = 1; k < pillars.size(); k++) {
                if (!pillars.get(k).isAfter(pillars.get(k - 1))) {
                    throw new QfError("E_INPUT", "pillars not strictly increasing on " + c.name(), "instruments");
                }
            }
            b.pillars = pillars.toArray(new LocalDate[0]);
            c.shape().check(c.interpolation(), b.pillars);
        }
    }

    // ---- solve ----

    private static final double ACCEPT = 1e-13;
    private static final double TARGET = 1e-15;
    private static final double H_NEWTON = 1e-7;
    private static final double H_JACOBIAN = 1e-5;

    private static double[] shifted(double[] x, int k, double h) {
        double[] y = x.clone();
        y[k] += h;
        return y;
    }

    /** Fourth-order central difference: (8 (f(h) - f(-h)) - (f(2h) - f(-2h))) / (12 h). */
    private static double[] stencil(java.util.function.DoubleFunction<double[]> f) {
        double h = H_JACOBIAN;
        double[] p1 = f.apply(h);
        double[] m1 = f.apply(-h);
        double[] p2 = f.apply(2 * h);
        double[] m2 = f.apply(-2 * h);
        double[] d = new double[p1.length];
        for (int i = 0; i < d.length; i++) {
            d[i] = (8.0 * (p1[i] - m1[i]) - (p2[i] - m2[i])) / (12.0 * h);
        }
        return d;
    }

    private static Discounting[] buildAll(Block[] blocks, double[] x, int upTo) {
        Discounting[] built = new Discounting[blocks.length];
        for (int i = 0; i <= upTo; i++) {
            built[i] = blocks[i].build(x);
        }
        return built;
    }

    private static double[] blockResiduals(Block b, Discounting[] built) {
        double[] r = new double[b.models.length];
        for (int k = 0; k < r.length; k++) {
            r[k] = b.models[k].residual(built);
        }
        return r;
    }

    private static double norm(double[] r) {
        double m = 0.0;
        for (double v : r) {
            if (Double.isNaN(v)) {
                return Double.NaN;
            }
            m = Math.max(m, Math.abs(v));
        }
        return m;
    }

    /** Residuals of block {@code b} with only its own unknowns varied; earlier curves held as built. */
    private static double[] residualsAt(Block[] blocks, Discounting[] earlier, int b, double[] x) {
        Discounting[] built = earlier.clone();
        built[b] = blocks[b].build(x);
        return blockResiduals(blocks[b], built);
    }

    private static double[][] ownJacobian(Block[] blocks, Discounting[] earlier, int bi, double[] x, double h) {
        Block b = blocks[bi];
        double[][] a = new double[b.size][b.size];
        for (int c = 0; c < b.size; c++) {
            double[] up = x.clone();
            double[] down = x.clone();
            up[b.offset + c] += h;
            down[b.offset + c] -= h;
            double[] ru = residualsAt(blocks, earlier, bi, up);
            double[] rd = residualsAt(blocks, earlier, bi, down);
            for (int i = 0; i < b.size; i++) {
                a[i][c] = (ru[i] - rd[i]) / (2.0 * h);
            }
        }
        return a;
    }

    private static Result run(LocalDate asOf, Block[] blocks, List<InstrumentSpec> instruments, int total) {
        double[] x = new double[total];
        // starting point: flat at the first quote of each curve
        for (Block b : blocks) {
            double q0 = instruments.get(b.instruments[0]).quote();
            if (b.spec.type() == CurveType.OIS_STEPS) {
                InstrumentSpec first = instruments.get(b.instruments[0]);
                double r0 = first.type() == InstrumentType.FUTURE ? (100.0 - q0) / 100.0 : q0;
                for (int k = 0; k < 1 + b.spec.stepDates().length; k++) {
                    x[b.offset + k] = r0;
                }
            } else {
                double r0 = b.spec.type() == CurveType.XCCY ? 0.0
                        : instruments.get(b.instruments[0]).type() == InstrumentType.FUTURE ? (100.0 - q0) / 100.0 : q0;
                for (int k = 0; k < b.pillars.length; k++) {
                    x[b.offset + k] = -r0 * ChronoUnit.DAYS.between(asOf, b.pillars[k]) / 365.0;
                }
            }
        }
        double worst = 0.0;
        for (int bi = 0; bi < blocks.length; bi++) {
            Discounting[] earlier = buildAll(blocks, x, bi - 1);
            Block b = blocks[bi];
            double[] r = residualsAt(blocks, earlier, bi, x);
            double err = norm(r);
            double[] best = x.clone();
            double bestErr = err;
            int stalled = 0;
            for (int it = 0; it < 80 && bestErr > TARGET && stalled < 4; it++) {
                double[][] a = ownJacobian(blocks, earlier, bi, x, H_NEWTON);
                double[] step;
                try {
                    step = LinearAlgebra.solve(a, r);
                } catch (QfError e) {
                    throw new QfError("E_NO_CONVERGENCE", "joint Jacobian is singular");
                }
                double lambda = 1.0;
                double[] trial = null;
                double[] rt = null;
                double et = Double.NaN;
                for (int ls = 0; ls < 30; ls++) {
                    trial = x.clone();
                    for (int i = 0; i < b.size; i++) {
                        trial[b.offset + i] -= lambda * step[i];
                    }
                    rt = residualsAt(blocks, earlier, bi, trial);
                    et = norm(rt);
                    if (!Double.isNaN(et) && (et < err || err < 1e-12)) {
                        break;
                    }
                    lambda /= 2.0;
                }
                x = trial;
                r = rt;
                err = et;
                if (err < bestErr) {
                    bestErr = err;
                    best = x.clone();
                    stalled = 0;
                } else {
                    stalled++;
                }
            }
            x = best;
            if (!(bestErr <= ACCEPT)) {
                throw new QfError("E_NO_CONVERGENCE", "joint solve stopped at " + bestErr + " on " + b.spec.name());
            }
            worst = Math.max(worst, bestErr);
        }
        Discounting[] built = buildAll(blocks, x, blocks.length - 1);
        // xccy dR/dq: d L_foreign / d spread = sum alpha_i D_f(e_i)
        for (Block b : blocks) {
            if (b.spec.type() == CurveType.XCCY) {
                for (int k = 0; k < b.instruments.length; k++) {
                    InstrumentSpec s = instruments.get(b.instruments[k]);
                    List<LocalDate> dates = Xccy.schedule(b.spec.start(), s.months());
                    double sum = 0.0;
                    for (int i = 1; i < dates.size(); i++) {
                        sum += ChronoUnit.DAYS.between(dates.get(i - 1), dates.get(i)) / 360.0
                                * built[b.index].discount(dates.get(i));
                    }
                    b.dRdq[k] = sum;
                }
            }
        }
        return outputs(blocks, instruments, x, built, total, worst);
    }

    private static Result outputs(Block[] blocks, List<InstrumentSpec> instruments, double[] x, Discounting[] built,
                                  int total, double worst) {
        int nq = instruments.size();
        // instrument index -> (block, row)
        int[] blockOf = new int[nq];
        int[] rowOf = new int[nq];
        for (Block b : blocks) {
            for (int k = 0; k < b.instruments.length; k++) {
                blockOf[b.instruments[k]] = b.index;
                rowOf[b.instruments[k]] = k;
            }
        }
        // dR/dx blocks: A[a][c] = d R_a / d x_c for c <= a; later blocks are exact zeros.
        double[][][][] a = new double[blocks.length][blocks.length][][];
        for (int bi = 0; bi < blocks.length; bi++) {
            Block rows = blocks[bi];
            for (int ci = 0; ci <= bi; ci++) {
                Block cols = blocks[ci];
                double[][] m = new double[rows.size][cols.size];
                for (int c = 0; c < cols.size; c++) {
                    int col = cols.offset + c;
                    int upTo = bi;
                    double[] d = stencil(h -> blockResiduals(rows, buildAll(blocks, shifted(x, col, h), upTo)));
                    for (int i = 0; i < rows.size; i++) {
                        m[i][c] = d[i];
                    }
                }
                a[bi][ci] = m;
            }
        }
        double[][] jac = new double[total][nq];
        for (int j = 0; j < nq; j++) {
            int qb = blockOf[j];
            double dq = blocks[qb].dRdq[rowOf[j]];
            double[][] sol = new double[blocks.length][];
            for (int bi = qb; bi < blocks.length; bi++) {
                Block b = blocks[bi];
                double[] rhs = new double[b.size];
                if (bi == qb) {
                    rhs[rowOf[j]] = -dq;
                }
                for (int ci = qb; ci < bi; ci++) {
                    double[][] m = a[bi][ci];
                    for (int i = 0; i < b.size; i++) {
                        double s = 0.0;
                        for (int c = 0; c < m[i].length; c++) {
                            s += m[i][c] * sol[ci][c];
                        }
                        rhs[i] -= s;
                    }
                }
                sol[bi] = LinearAlgebra.solve(a[bi][bi], rhs);
                for (int i = 0; i < b.size; i++) {
                    jac[b.offset + i][j] = sol[bi][i];
                }
            }
        }
        List<String> unknowns = new ArrayList<>();
        List<SolvedCurve> curves = new ArrayList<>();
        List<TurnFactor> turnFactors = new ArrayList<>();
        List<double[]> sens = new ArrayList<>();
        for (Block b : blocks) {
            String nm = b.spec.name();
            int nMain = b.size - b.turns.length;
            if (b.spec.type() == CurveType.OIS_STEPS) {
                unknowns.add(nm + ":base");
                for (LocalDate d : b.spec.stepDates()) {
                    unknowns.add(nm + ":step:" + d);
                }
                curves.add(new SolvedCurve(nm, null, null, x[b.offset],
                        Arrays.copyOfRange(x, b.offset + 1, b.offset + nMain)));
            } else {
                double[] df = new double[b.pillars.length];
                for (int k = 0; k < df.length; k++) {
                    unknowns.add(nm + ":pillar:" + b.pillars[k]);
                    df[k] = Math.exp(x[b.offset + k]);
                }
                curves.add(new SolvedCurve(nm, b.pillars, df, null, null));
            }
            for (int t = 0; t < b.turns.length; t++) {
                LocalDate td = b.turns[t];
                unknowns.add(nm + ":turn:" + td);
                int col = b.offset + nMain + t;
                turnFactors.add(new TurnFactor(nm, td, Math.exp(x[col])));
                double[] row = new double[nq];
                Set<Integer> mine = new HashSet<>();
                for (int k = 0; k < b.instruments.length; k++) {
                    mine.add(b.instruments[k]);
                }
                for (int j = 0; j < nq; j++) {
                    int jb = blockOf[j];
                    LocalDate[] span = blocks[jb].spans[rowOf[j]];
                    boolean straddles = !span[0].isAfter(td) && span[1].isAfter(td);
                    if (!mine.contains(j) || !straddles) {
                        row[j] = 0.0;
                        continue;
                    }
                    Model model = blocks[jb].models[rowOf[j]];
                    row[j] = stencil(h -> new double[] {model.residual(buildAll(blocks, shifted(x, col, h), jb))})[0];
                }
                sens.add(row);
            }
        }
        List<String> quotes = new ArrayList<>();
        for (InstrumentSpec s : instruments) {
            quotes.add(s.id());
        }
        return new Result(curves, turnFactors, unknowns, quotes, jac, sens.toArray(new double[0][]), worst);
    }

    /** rates.funding.curve: spreads, pillars and discount factors (joint-solve-and-funding.md). */
    public record Funding(double[] spreads, LocalDate[] pillars, double[] pillarFactors, double[] discountFactors) {}

    public static Funding funding(Curve ois, LocalDate[] ends, double[] rates, LocalDate[] dates) {
        Finite.check("rates", rates);
        if (ends.length == 0) {
            throw new QfError("E_INPUT", "no quotes", "quotes");
        }
        LocalDate asOf = ois.asOf();
        LocalDate previous = asOf;
        for (LocalDate e : ends) {
            if (!e.isAfter(previous)) {
                throw new QfError("E_INPUT", "quote ends must increase from as_of", "quotes");
            }
            previous = e;
        }
        int n = ends.length;
        double[] t = new double[n + 1];
        double[] lnRatio = new double[n + 1];
        for (int i = 0; i < n; i++) {
            long days = ChronoUnit.DAYS.between(asOf, ends[i]);
            double g = 1.0 + rates[i] * days / 360.0;
            if (!(g > 0.0)) {
                throw new QfError("E_DOMAIN", "1 + rate * alpha must be positive", "quotes");
            }
            t[i + 1] = days / 365.0;
            lnRatio[i + 1] = Math.log(ois.discount(ends[i])) + Math.log(g);
        }
        for (LocalDate d : dates) {
            if (d.isBefore(asOf)) {
                throw new QfError("E_OUT_OF_RANGE", "date is before as_of", "dates");
            }
        }
        double[] s = new double[n];
        double[] cum = new double[n + 1];
        for (int i = 0; i < n; i++) {
            s[i] = (lnRatio[i + 1] - lnRatio[i]) / (t[i + 1] - t[i]);
            cum[i + 1] = cum[i] + s[i] * (t[i + 1] - t[i]);
        }
        double[] pf = new double[n];
        for (int i = 0; i < n; i++) {
            pf[i] = ois.discount(ends[i]) * Math.exp(-cum[i + 1]);
        }
        double[] df = new double[dates.length];
        for (int k = 0; k < df.length; k++) {
            double tk = ois.time(dates[k]);
            double integral;
            int i = 0;
            while (i < n && t[i + 1] < tk) {
                i++;
            }
            if (i == n) {
                integral = cum[n] + s[n - 1] * (tk - t[n]);
            } else {
                integral = cum[i] + s[i] * (tk - t[i]);
            }
            df[k] = ois.discount(dates[k]) * Math.exp(-integral);
        }
        return new Funding(s, ends.clone(), pf, df);
    }
}
