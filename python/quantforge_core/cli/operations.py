"""The operation table. Importing the handler modules registers every verb (registry.py); the
table is REGISTRY itself, so it cannot drift from the handlers."""
from . import (  # noqa: F401 - imported to register their verbs
    ops_bonds,
    ops_calibration,
    ops_commodity,
    ops_core,
    ops_credit,
    ops_equity,
    ops_exotics,
    ops_fx,
    ops_hedging,
    ops_inflation,
    ops_mbs,
    ops_rates,
    ops_risk,
    ops_usecases,
    ops_vol,
)
from .registry import REGISTRY, execute

OPERATIONS = REGISTRY
__all__ = ["OPERATIONS", "execute"]
