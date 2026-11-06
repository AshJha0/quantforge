# Data contracts

## Common metadata
`schema_version`, `instrument_id`, `source_id`, `event_time`, `receive_time`, `timezone`, `currency`, `unit`, `snapshot_id`, `quality_flags`.

## Quote
`bid`, `ask`, optional `bid_size`, `ask_size`, `quote_status`, `market_timestamp`.

## Trade
`price`, `quantity`, `aggressor_side` when available, `venue`, `trade_timestamp`, `trade_id`.

## Calculation provenance
`calculation_id`, `input_snapshot_id`, `model_name`, `model_version`, `configuration_hash`, `calculation_time`, `result_status`, `diagnostics`.

## Rules
- Timestamp semantics must distinguish event time from receive time.
- Missing, stale, crossed and indicative quotes must be represented explicitly.
- Decimal precision and rounding policy must be documented by instrument class.
- Do not encode missing values as zero.
- Version schemas and define backward-compatibility rules.
