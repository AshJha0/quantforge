// CLI handlers, stage H multi-asset (H-22 equities, H-23 FX spot, H-24 rates): specifications/09-microstructure/
// asset-conventions.md, 10-execution/auction.md, fx-rfq-venue.md, rates-futures-venue.md. The gate (array limit,
// finite rule) runs first, as the Python registry's does on core access; the library then parses every field
// in the reference order (HR-66) and writes the labelled outputs (HR-94).

#define QF_MA_OP(name, fn)                       \
    void name(const In& in, Out& out) {          \
        in.ready();                              \
        micro::ma::fn(in.raw(), out.values);     \
    }
QF_MA_OP(op_ma_eq_round_price, eq_round_price)
QF_MA_OP(op_ma_eq_fee_check, eq_fee_check)
QF_MA_OP(op_ma_eq_round_lot, eq_round_lot)
QF_MA_OP(op_ma_eq_settle_date, eq_settle_date)
QF_MA_OP(op_ma_auction_uncross, auction_uncross)
QF_MA_OP(op_ma_fx_pip_value, fx_pip_value)
QF_MA_OP(op_ma_fx_spot_date, fx_spot_date)
QF_MA_OP(op_ma_fx_stream, fx_stream)
QF_MA_OP(op_ma_fx_request, fx_request)
QF_MA_OP(op_ma_rates_parse_32nds, rates_parse_32nds)
QF_MA_OP(op_ma_rates_format_32nds, rates_format_32nds)
QF_MA_OP(op_ma_rates_tick_value, rates_tick_value)
QF_MA_OP(op_ma_rates_bond_price, rates_bond_price)
QF_MA_OP(op_ma_rates_bill_price, rates_bill_price)
QF_MA_OP(op_ma_rates_bond_yield, rates_bond_yield)
QF_MA_OP(op_ma_fut_to_ticks, fut_to_ticks)
QF_MA_OP(op_ma_fut_to_text, fut_to_text)
QF_MA_OP(op_ma_fut_pnl, fut_pnl)
QF_MA_OP(op_ma_fut_variation, fut_variation)
QF_MA_OP(op_ma_fut_run, fut_run)
#undef QF_MA_OP

constexpr Entry multiasset_ops[] = {
    {"exec.sim.auction.uncross", op_ma_auction_uncross},
    {"exec.sim.fut.pnl", op_ma_fut_pnl},
    {"exec.sim.fut.run", op_ma_fut_run},
    {"exec.sim.fut.to_text", op_ma_fut_to_text},
    {"exec.sim.fut.to_ticks", op_ma_fut_to_ticks},
    {"exec.sim.fut.variation", op_ma_fut_variation},
    {"exec.sim.fx.request", op_ma_fx_request},
    {"exec.sim.fx.stream", op_ma_fx_stream},
    {"micro.eq.fee_check", op_ma_eq_fee_check},
    {"micro.eq.round_lot", op_ma_eq_round_lot},
    {"micro.eq.round_price", op_ma_eq_round_price},
    {"micro.eq.settle_date", op_ma_eq_settle_date},
    {"micro.fx.pip_value", op_ma_fx_pip_value},
    {"micro.fx.spot_date", op_ma_fx_spot_date},
    {"micro.rates.bill_price", op_ma_rates_bill_price},
    {"micro.rates.bond_price", op_ma_rates_bond_price},
    {"micro.rates.bond_yield", op_ma_rates_bond_yield},
    {"micro.rates.format_32nds", op_ma_rates_format_32nds},
    {"micro.rates.parse_32nds", op_ma_rates_parse_32nds},
    {"micro.rates.tick_value", op_ma_rates_tick_value},
};
