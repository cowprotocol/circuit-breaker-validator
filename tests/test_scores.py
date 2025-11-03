"""Tests for score computation"""

from unittest.mock import Mock

import pytest
from hexbytes import HexBytes

from circuit_breaker_validator.models import (
    OnchainTrade,
    OffchainTrade,
    OnchainSettlementData,
    OffchainSettlementData,
)
from circuit_breaker_validator.scores import compute_score


@pytest.mark.parametrize(
    "order_type,surplus_token,expected_score",
    [
        # Sell order (surplus in buy token)
        ("sell", "buy", 6 * 10**19),
        # Buy order (surplus in sell token)
        ("buy", "sell", 6 * 10**9),
    ],
)
def test_compute_score(order_type, surplus_token, expected_score):
    """Test compute_score for different order types and surplus tokens."""
    sell_token = HexBytes("0x01")
    buy_token = HexBytes("0x02")
    order_uid = HexBytes("0x03")
    raw_surplus = 2 * 10**19
    price = 3 * 10**18
    limit_sell_amount = 10**20
    limit_buy_amount = 10**10

    offchain_trade = Mock(spec=OffchainTrade)
    offchain_trade.order_uid = order_uid

    # Create trade based on order type
    if order_type == "sell":
        # Sell order (surplus in buy token)
        trade = Mock(spec=OnchainTrade)
        trade.order_uid = order_uid
        trade.raw_surplus = Mock(return_value=raw_surplus)
        trade.sell_token = sell_token
        trade.buy_token = buy_token
        trade.surplus_token = Mock(return_value=trade.buy_token)
    else:
        # Buy order (surplus in sell token)
        trade = Mock(spec=OffchainTrade)
        trade.order_uid = order_uid
        trade.raw_surplus = Mock(return_value=raw_surplus)
        trade.sell_token = sell_token
        trade.buy_token = buy_token
        trade.limit_sell_amount = limit_sell_amount
        trade.limit_buy_amount = limit_buy_amount
        trade.surplus_token = Mock(return_value=trade.sell_token)

    onchain_data = Mock(spec=OnchainSettlementData)
    onchain_data.trades = [trade]
    onchain_data.native_prices = {buy_token: price}

    offchain_data = Mock(spec=OffchainSettlementData)
    offchain_data.trades = [offchain_trade]
    offchain_data.trade_fee_policies = {}
    offchain_data.native_prices = {buy_token: price}

    assert compute_score(onchain_data, offchain_data) == expected_score


@pytest.mark.parametrize(
    "auction_id,tx_hash,solver,order_uid,sell_token,buy_token,raw_surplus,expected_score",
    [
        (
            1,
            HexBytes("0x00"),
            HexBytes("0x01"),
            HexBytes("0x02"),
            HexBytes("0x03"),
            HexBytes("0x04"),
            0,
            0,
        ),
    ],
)
def test_compute_score_missing_native_price(
    auction_id,
    tx_hash,
    solver,
    order_uid,
    sell_token,
    buy_token,
    raw_surplus,
    expected_score,
):
    "Test for scores being zero for trades with missing native price"
    offchain_trade = Mock(spec=OffchainTrade)
    offchain_trade.order_uid = order_uid

    trade = Mock(spec=OnchainTrade)
    trade.order_uid = order_uid
    trade.raw_surplus = Mock(return_value=raw_surplus)
    trade.sell_token = sell_token
    trade.buy_token = buy_token
    trade.surplus_token = Mock(return_value=trade.buy_token)

    onchain_data = OnchainSettlementData(auction_id, tx_hash, solver, [trade])

    offchain_data = Mock(spec=OffchainSettlementData)
    offchain_data.trades = [offchain_trade]
    offchain_data.trade_fee_policies = {}
    offchain_data.native_prices = {}

    assert compute_score(onchain_data, offchain_data) == expected_score
