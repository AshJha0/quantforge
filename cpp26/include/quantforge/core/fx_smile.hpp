#pragma once
// Stage E, E3: Garman-Kohlhagen vanillas, FX delta and ATM conventions, smile from quotes
// (05-volatility/fx-smile.md). Rulings E-A9 to E-A11.
#include "quantforge/core/models.hpp"

namespace quantforge {

/// Spot is domestic per unit foreign; rates flat continuous; T runs to expiry and delivery together.
struct GkMarket {
    double spot, expiry_years, domestic_rate, foreign_rate;
    double forward() const;
};

enum class FxDeltaType { Spot, Forward, SpotPa, ForwardPa };
enum class FxAtmType { Spot, Forward, Dns };

struct GkPrice {
    double price, premium_pct_foreign, forward, delta, gamma, vega;
};
GkPrice fx_option_price(const GkMarket& m, double strike, double vol, OptionType type, double notional);

/// One delta of the given type at a strike (inputs checked by the caller).
double fx_delta(const GkMarket& m, double strike, double vol, OptionType type, FxDeltaType dt);
struct FxDeltas {
    double spot, forward, spot_pa, forward_pa;
};
FxDeltas fx_deltas_from_strike(const GkMarket& m, double strike, double vol, OptionType type);
double fx_delta_to_strike(const GkMarket& m, double vol, OptionType type, double delta, FxDeltaType dt);
double fx_atm_strike(const GkMarket& m, double vol, FxAtmType atm, FxDeltaType dt);

struct FxSmile {
    double atm_strike, call_vol, put_vol, call_strike, put_strike;
};
FxSmile fx_smile_from_quotes(const GkMarket& m, double atm_vol, double rr, double bf, double delta, FxDeltaType dt,
                             FxAtmType atm);

}  // namespace quantforge
