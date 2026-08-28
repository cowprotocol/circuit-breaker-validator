# Circuit Breaker Validator Library

A Python library for validating CoW Protocol settlement transactions. This library provides core validation logic to ensure solver settlements comply with CoW Protocol rules by comparing on-chain execution data with off-chain auction proposals.

## Overview

The Competition Monitoring library enforces three main validation rules for settlement transactions:

1. **Solver Identity Verification** - Ensures the on-chain settlement was submitted by the winning solver
2. **Order Validation** - Validates that executed trades match what was proposed in the bid
3. **Hook Validation** - Validates that pre/post hooks declared in appData were executed

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
  - `order_hooks`: Dict mapping order_uid to expected hooks for that order

- **`OnchainTrade`** - Executed trade data
- **`OffchainTrade`** - Proposed trade data

### Validation Functions (`check_tx.py`)

#### `inspect(onchain_data, offchain_data) -> None`

Main validation orchestrator that runs all checks. Raises `InvalidSettlement` if any check fails.

#### Individual Check Functions

- **`check_solver(onchain_data, offchain_data) -> bool`**
  - Validates solver address matches between on-chain and off-chain data

- **`check_orders(onchain_data, offchain_data) -> bool`**
  - Performs two ordered checks:
    1. **1-to-1 Mapping** - Executed trades must exactly match proposed trades
    2. **Amount Matching** - Sell/buy amounts must match between execution and proposal

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
- Hooks declared for each order (for `check_hooks`)

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
            already_executed_amount=0,
        )
    ],
    order_hooks={},
)

# Validate settlement
try:
    inspect(onchain_data, offchain_data)
    print("✅ Settlement passed all validation checks")
except InvalidSettlement as e:
    print(f"❌ Settlement validation failed: {e}")
```
