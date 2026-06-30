"""Test models"""

from unittest.mock import Mock

import pytest

from circuit_breaker_validator.models import (
    OnchainTrade,
)

@pytest.mark.parametrize(
    "kind,sell_amount,buy_amount,limit_sell_amount,limit_buy_amount,expected_surplus",
    [
        # sell order
        ("sell", 50, 5100, 100, 10000, 100),
        # buy order
        ("buy", 49, 5000, 100, 10000, 1),
    ],
)
def test_trade_surplus(
    kind, sell_amount, buy_amount, limit_sell_amount, limit_buy_amount, expected_surplus
):
    """Test surplus calculation for different order kinds."""
    trade = Mock(spec=OnchainTrade)
    trade.sell_amount = sell_amount
    trade.buy_amount = buy_amount
    trade.limit_sell_amount = limit_sell_amount
    trade.limit_buy_amount = limit_buy_amount
    trade.kind = kind

    assert OnchainTrade.surplus(trade) == expected_surplus


