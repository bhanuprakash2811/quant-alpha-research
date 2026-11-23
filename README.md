# Quant Alpha Research

A modular quantitative research platform focused on market data infrastructure, market microstructure, order-flow analytics, and systematic alpha research.

The project is designed to build a reliable foundation for processing market events, maintaining order book state, extracting microstructure features, and developing quantitative trading research workflows.

## Current Capabilities

### 1. Market Data Infrastructure
- Structured market event schemas using Pydantic.
- Trade and order book snapshot validation.
- OHLCV market data validation.
- Timestamp and instrument consistency checks.

### 2. Streaming Infrastructure
- Asynchronous event processing.
- Event bus with bounded queue capacity.
- FIFO event delivery.
- Backpressure handling.
- Graceful shutdown and consumer lifecycle management.

### 3. Market Depth and Order Book
- Order book snapshot management.
- Incremental bid/ask updates.
- Price-level insertion and deletion.
- Sequence number validation.
- Recovery from invalid order book states.

### 4. Market Microstructure
- Mid-price calculation.
- Microprice calculation.
- Bid-ask spread and spread in basis points.
- Depth imbalance.
- Weighted depth imbalance.
- Liquidity concentration analysis.

### 5. Order Flow Analytics
- Order Flow Imbalance (OFI).
- Bid-side and ask-side contribution analysis.
- Timestamp and instrument consistency validation.

### 6. Trade Flow Analytics
- Buy and sell volume tracking.
- Trade delta calculation.
- Unknown trade classification.
- Cumulative volume delta (CVD).
- Session and interval statistics.

## Technology Stack

| Category | Technologies |
|---|---|
| Language | Python 3.11+ |
| Data Processing | NumPy, Pandas, Polars, PyArrow |
| Analytics | SciPy, Statsmodels |
| Storage / Query | DuckDB |
| Data Validation | Pydantic |
| Package Management | uv |
| Testing | pytest |
| Code Quality | Ruff, mypy |

## Architecture

```text
quant-alpha-research/
│
├── src/
│   └── quant_alpha/
│       ├── backtesting/
│       ├── data/
│       │   ├── streaming/
│       │   │   ├── consumer.py
│       │   │   └── event_bus.py
│       │   ├── schema.py
│       │   └── validation.py
│       │
│       ├── features/
│       │   ├── market_depth/
│       │   ├── market_state/
│       │   ├── microstructure/
│       │   ├── orderflow/
│       │   └── tradeflow/
│       │
│       └── research/
│
├── tests/
├── pyproject.toml
├── uv.lock
├── .python-version
└── README.md
```

## Getting Started

### Prerequisites

- Python 3.11 or later
- uv package manager

Install uv: https://docs.astral.sh/uv/

### Clone the repository

```bash
git clone https://github.com/bhanuprakash2811/quant-alpha-research.git
cd quant-alpha-research
```

### Install dependencies

```bash
uv sync --dev
```

### Run the test suite

```bash
uv run pytest -v
```

### Run static analysis

```bash
uv run ruff check src tests
uv run mypy src
```

## Testing

The current test suite contains 100 tests covering:

- Market event schemas and validation.
- Streaming consumers and event bus behavior.
- Order book snapshots and incremental updates.
- Market microstructure calculations.
- Order Flow Imbalance.
- Trade-flow statistics and CVD.

Latest local validation:

- 100 tests passed.
- Ruff checks passed.
- mypy checks passed across 21 source files.

## Development Roadmap

- [ ] Historical market data ingestion.
- [ ] High-performance market data storage.
- [ ] Advanced order-flow and liquidity features.
- [ ] Backtesting engine.
- [ ] Alpha signal research and evaluation.
- [ ] Transaction cost and slippage modeling.
- [ ] Walk-forward and out-of-sample validation.
- [ ] Performance and risk analytics.

## Disclaimer

This project is intended for software engineering, quantitative research, and educational purposes. It is not investment advice or a production-ready trading system. All trading strategies require rigorous validation, realistic transaction cost modeling, and out-of-sample testing.
