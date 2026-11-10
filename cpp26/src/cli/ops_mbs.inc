// CLI handlers, the mbs verbs.
// Included by dispatch.cpp inside its unnamed namespace; not a translation unit of its own.

void op_mbs_cashflows(const In& in, Out& out) {
    const MbsPool p = pool_of(in);
    in.ready();
    const MbsCashflows c = mbs_cashflows(p);
    out.key_reals("balance", c.balance);
    out.key_reals("interest", c.interest);
    out.key_reals("scheduled_principal", c.scheduled_principal);
    out.key_reals("prepayment", c.prepayment);
    out.key_real("wal", c.wal);
}

void op_mbs_price(const In& in, Out& out) {
    const MbsPool p = pool_of(in);
    const double y = in.real("yield");
    const long long delay = in.integer("delay_days");
    in.ready();
    const MbsPrice r = mbs_price(p, y, delay);
    out.key_real("price", r.price);
    out.key_real("modified_duration", r.modified_duration);
    out.key_real("wal", r.wal);
}

constexpr Entry mbs_ops[] = {
    {"mbs.cashflows", op_mbs_cashflows},
    {"mbs.price", op_mbs_price},
};
