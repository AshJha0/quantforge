# Domain boundaries

| Domain | Owns | Does not own |
|---|---|---|
| Core | Types, units, errors, time, calendars, numerical primitives | Product pricing |
| Market data | Quote/trade/order-book schemas, normalisation, snapshots | Model calibration |
| Curves | Curve representations, bootstrap, interpolation, dependencies | Product valuation |
| Calibration | Objective functions, optimisers, diagnostics, parameter fitting | Market-data ingestion |
| Pricing | Instrument valuation and model interfaces | Portfolio limits |
| Volatility | Implied vol, smiles, surfaces and vol models | Execution routing |
| Risk | Sensitivities, scenarios, VaR/ES and aggregation contracts | Hedge execution |
| Portfolio | Positions, exposures, attribution and aggregation | Venue microstructure |
| Hedging | Hedge selection and constrained optimisation | Order-book reconstruction |
| Microstructure | Books, queue, flow, liquidity and fill models | Portfolio accounting |
| Execution | Benchmarks, cost, impact and execution simulation | Curve construction |
| Research | Replay, backtesting, validation and reporting orchestration | Duplicate domain formulas |
| Platform | APIs, configuration, observability and deployment | Quantitative model ownership |
