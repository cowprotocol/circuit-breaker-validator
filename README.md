# Circuit Braker Validator Library

A Python library for validating CoW Protocol settlement transactions. This library provides core validation logic to ensure solver settlements comply with CoW Protocol rules by comparing on-chain execution data with off-chain auction proposals.

## Overview

The Competition Monitoring library enforces three main validation rules for settlement transactions:

1. **Solver Identity Verification** - Ensures the on-chain settlement was submitted by the winning solver
2. **Order Validation** - Validates trade execution, amounts, and surplus rules
3. **Score Validation** - Verifies computed scores match reported auction scores

## Core Components

### Data Models (`models.py`)

- **`OnchainSettlementData`** - Settlement data from blockchain
  - `auction_id`: Auction identifier
  - `tx_hash`: Transaction hash
  - `solver`: Solver address
  - `trades`: List of executed trades

- **`OffchainSettlementData`** - Settlement data from orderbook
  - `auction_id`: Auction identifier
  - `solver`: Winning solver address
  - `trades`: List of proposed trades
  - `score`: Reported auction score
  - `trade_fee_policies`: Fee policies per order
  - `valid_orders`: Set of valid order UIDs
  - `jit_order_addresses`: Whitelisted JIT order addresses
  - `native_prices`: Token prices in native currency

- **`OnchainTrade`** - Executed trade data
- **`OffchainTrade`** - Proposed trade data
- **`Quote`** - Quote information for price improvement calculation
- **Fee Policy Models** - `VolumeFeePolicy`, `SurplusFeePolicy`, `PriceImprovementFeePolicy`

### Validation Functions (`check_tx.py`)

#### `inspect(onchain_data, offchain_data) -> None`

Main validation orchestrator that runs all checks. Raises `InvalidSettlement` if any check fails.

#### Individual Check Functions

- **`check_solver(onchain_data, offchain_data) -> bool`**
  - Validates solver address matches between on-chain and off-chain data

- **`check_orders(onchain_data, offchain_data) -> bool`**
  - Performs three ordered checks:
    1. **1-to-1 Mapping** - Executed trades must exactly match proposed trades
    2. **Amount Matching** - Sell/buy amounts must match between execution and proposal
    3. **Surplus Validation** - Orders with surplus must be valid or whitelisted JIT orders

- **`check_score(onchain_data, offchain_data) -> bool`**
  - Validates computed score matches reported auction score (within threshold)

### Score Computation (`scores.py`)

#### `compute_score(onchain_data, offchain_data) -> int`

Computes the settlement score by summing raw surplus values across all trades.

### Exceptions (`exceptions.py`)

- **`InvalidSettlement`** - Raised when settlement violates protocol rules
- **`WhitelistedSolver`** - Raised when solver is whitelisted (skip validation)
- **`CriticalDataFetchingError`** - Critical error in data fetching
- **`NoncriticalDataFetchingError`** - Non-critical error (may retry)
- **`MissingOnchainData`** - On-chain data unavailable

### Constants (`constants.py`)

Protocol constants including:
- Contract addresses (`SETTLEMENT_CONTRACT_ADDRESS`, `GPV2_AUTHENTICATOR`, etc.)
- Chain-specific configurations (`CHAIN_ID_TO_ZODIAC_MODULE_ADDRESS`)
- Call signatures and special addresses

## Validation Rules

### 1. Solver Verification
- On-chain solver address must match off-chain winning solver
- Whitelisted solvers (team multisig) skip validation

### 2. Order Validation

The library enforces strict 1-to-1 trade mapping:

#### 2a. 1-to-1 Mapping
- Every executed trade must have been proposed in the bid
- Every proposed trade must be executed
- **All JIT orders must be revealed during bidding**, regardless of surplus

#### 2b. Amount Matching
- `onchain.sell_amount == offchain.sell_amount`
- `onchain.buy_amount == offchain.buy_amount`
- No deviation allowed from proposed amounts

#### 2c. Surplus Validation
- Orders with non-zero surplus must either:
  - Be part of the auction (in `valid_orders`), OR
  - Have whitelisted JIT order owner (in `jit_order_addresses`)

### 3. Score Validation
- Computed score must not be much lower or much higher than reported score:
- Upper Threshold: `10^12` atoms (`SCORE_CHECK_UPPER_THRESHOLD`); corresponds to over-reporting
- Lower Threshold: `10^11` atoms (`SCORE_CHECK_LOWER_THRESHOLD`); corresponds to under-reporting


## Integration Guide

To use this library in a monitoring system like Circuit Breaker, you need to provide:

### 1. On-chain Data Fetcher
Implement a component to fetch settlement data from blockchain:
- Transaction details and receipts
- Decoded settlement calldata
- Trade events from transaction logs

### 2. Off-chain Data Fetcher
Implement a component to fetch auction data:
- Winning solver and solution details
- Proposed trades and amounts
- Fee policies for each order
- Valid order UIDs and JIT order addresses
- Native token prices

### 3. Settlement Processor
Use the library's `inspect()` function to validate settlements:

### 4. Error Handling
Handle the library's exceptions appropriately:
- `InvalidSettlement` - Settlement violated rules → blacklist solver
- `WhitelistedSolver` - Whitelisted solver → skip validation
- Data fetching errors - Retry or log for manual review


## Running Tests

```bash
python -m pytest tests/
```

## Usage Example

```python
# Create onchain settlement data
onchain_data = OnchainSettlementData(
    auction_id=12345,
    tx_hash=HexBytes("0x..."),
    solver=HexBytes("0xSOLVER_ADDRESS"),
    trades=[
        OnchainTrade(
            order_uid=HexBytes("0xORDER_UID"),
            sell_amount=1000000,
            buy_amount=2000000,
            owner=HexBytes("0xOWNER"),
            sell_token=HexBytes("0xTOKEN_A"),
            buy_token=HexBytes("0xTOKEN_B"),
            limit_sell_amount=1000000,
            limit_buy_amount=1900000,
            kind="sell",
        )
    ],
)

# Create offchain settlement data
offchain_data = OffchainSettlementData(
    auction_id=12345,
    solver=HexBytes("0xSOLVER_ADDRESS"),
    trades=[
        OffchainTrade(
            order_uid=HexBytes("0xORDER_UID"),
            sell_amount=1000000,
            buy_amount=2000000,
        )
    ],
    score=100000000000000000,
    trade_fee_policies={},
    valid_orders={HexBytes("0xORDER_UID")},
    jit_order_addresses=set(),
    native_prices={HexBytes("0xTOKEN_B"): 1000000000000000000},
)

# Validate settlement
try:
    inspect(onchain_data, offchain_data)
    print("✅ Settlement passed all validation checks")
except InvalidSettlement as e:
    print(f"❌ Settlement validation failed: {e}")
```
