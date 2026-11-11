package org.quantforge.pricing;

import java.util.Arrays;

/**
 * A minimal reverse-mode automatic differentiation tape (aad-core.md, ruling G-9). Every node stores its value and
 * up to two parents with their local partial derivatives; {@link #gradient} sweeps the tape once backwards.
 * Nodes are plain {@code int} indices so the forward pass allocates no objects.
 */
public final class Tape {
    private double[] val = new double[1 << 16];
    private int[] p1 = new int[1 << 16];
    private int[] p2 = new int[1 << 16];
    private double[] d1 = new double[1 << 16];
    private double[] d2 = new double[1 << 16];
    private int n;

    /** An empty tape. */
    public Tape() {}

    private int push(double v, int a, double da, int b, double db) {
        if (n == val.length) {
            int len = val.length * 2;
            val = Arrays.copyOf(val, len);
            p1 = Arrays.copyOf(p1, len);
            p2 = Arrays.copyOf(p2, len);
            d1 = Arrays.copyOf(d1, len);
            d2 = Arrays.copyOf(d2, len);
        }
        val[n] = v;
        p1[n] = a;
        d1[n] = da;
        p2[n] = b;
        d2[n] = db;
        return n++;
    }

    /**
     * An input or a constant: a node with no parents.
     *
     * @param v its value
     * @return the node
     */
    public int input(double v) {
        return push(v, -1, 0.0, -1, 0.0);
    }

    /**
     * The value of a node.
     *
     * @param x the node
     * @return its value
     */
    public double value(int x) {
        return val[x];
    }

    int add(int a, int b) {
        return push(val[a] + val[b], a, 1.0, b, 1.0);
    }

    int sub(int a, int b) {
        return push(val[a] - val[b], a, 1.0, b, -1.0);
    }

    int mul(int a, int b) {
        return push(val[a] * val[b], a, val[b], b, val[a]);
    }

    int div(int a, int b) {
        double q = val[a] / val[b];
        return push(q, a, 1.0 / val[b], b, -q / val[b]);
    }

    int scale(int a, double c) {
        return push(val[a] * c, a, c, -1, 0.0);
    }

    int shift(int a, double c) {
        return push(val[a] + c, a, 1.0, -1, 0.0);
    }

    /** {@code c - a}. */
    int rsub(double c, int a) {
        return push(c - val[a], a, -1.0, -1, 0.0);
    }

    int exp(int a) {
        double e = Math.exp(val[a]);
        return push(e, a, e, -1, 0.0);
    }

    int expm1(int a) {
        return push(Math.expm1(val[a]), a, Math.exp(val[a]), -1, 0.0);
    }

    int log(int a) {
        return push(Math.log(val[a]), a, 1.0 / val[a], -1, 0.0);
    }

    int sqrt(int a) {
        double s = Math.sqrt(val[a]);
        return push(s, a, 0.5 / s, -1, 0.0);
    }

    /** The larger of two nodes, differentiated through the active branch (the first on a tie). */
    int max(int a, int b) {
        return val[a] >= val[b] ? a : b;
    }

    /**
     * Adjoints of every node with respect to {@code out}.
     *
     * @param out the output node
     * @return the adjoint array, indexed by node
     */
    public double[] gradient(int out) {
        double[] adj = new double[n];
        adj[out] = 1.0;
        for (int i = out; i >= 0; i--) {
            double g = adj[i];
            if (g == 0.0) {
                continue;
            }
            if (p1[i] >= 0) {
                adj[p1[i]] += g * d1[i];
            }
            if (p2[i] >= 0) {
                adj[p2[i]] += g * d2[i];
            }
        }
        return adj;
    }
}
