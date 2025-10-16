"""Test models"""

from unittest.mock import Mock, MagicMock

from fractions import Fraction
import math
import pytest

from circuit_breaker_validator.models import (
    OnchainTrade,
    OffchainTrade,
    VolumeFeePolicy,
    SurplusFeePolicy,
    PriceImprovementFeePolicy,
    Quote,
)


@pytest.mark.parametrize(
    "kind,expected_sell_amount,expected_buy_amount",
    [
        # sell order
        (
            "sell",
            100,  # sell_amount
            math.ceil(
                (100 - 1) * Fraction(10000, 100)
            ),  # (sell_amount - fee_amount) * exchange_rate
        ),
        # buy order
        ("buy", 100 + 1, 10000),  # sell_amount + fee_amount  # buy_amount
    ],
)
def test_quote_effective_amounts(kind, expected_sell_amount, expected_buy_amount):
    """Test effective sell and buy amounts for different order kinds."""
    sell_amount = 100
    buy_amount = 10000
    fee_amount = 1
    quote = Quote(sell_amount, buy_amount, fee_amount)

    assert quote.effective_sell_amount(kind=kind) == expected_sell_amount
    assert quote.effective_buy_amount(kind=kind) == expected_buy_amount


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


@pytest.mark.parametrize(
    "kind,amount_field,expected_volume",
    [
        # sell order (volume is buy_amount)
        ("sell", "buy_amount", 10**18),
        # buy order (volume is sell_amount)
        ("buy", "sell_amount", 10**18),
    ],
)
def test_trade_volume(kind, amount_field, expected_volume):
    """Test volume calculation for different order kinds."""
    trade = Mock(spec=OnchainTrade)
    setattr(trade, amount_field, expected_volume)
    trade.kind = kind

    assert OnchainTrade.volume(trade) == expected_volume


@pytest.mark.parametrize(
    "kind,sell_amount,buy_amount,quote_sell_amount,quote_buy_amount,quote_fee_amount,surplus_value,expected_improvement",
    [
        # Basic cases
        # sell order
        ("sell", 50, 5100, 100, 10000, 0, 100, 100),
        # buy order
        ("buy", 49, 5000, 100, 10000, 0, 1, 1),
        # Cases where surplus is smaller than quote price improvement
        # sell order: surplus (1) < quote improvement (2)
        ("sell", 100, 101, 100, 99, 0, 1, 1),
        # buy order: surplus (1) < quote improvement (2)
        ("buy", 99, 100, 101, 100, 0, 1, 1),
        # sell order: large difference - surplus (5) < quote improvement (10)
        ("sell", 100, 105, 100, 95, 0, 5, 5),
        # Edge case: sell order with zero surplus (0) < quote improvement (5)
        ("sell", 100, 100, 100, 95, 0, 0, 0),
    ],
)
def test_trade_price_improvement(
    kind,
    sell_amount,
    buy_amount,
    quote_sell_amount,
    quote_buy_amount,
    quote_fee_amount,
    surplus_value,
    expected_improvement,
):
    """Test price improvement calculation for different order kinds.

    This test verifies that price_improvement returns the minimum of:
    1. Quote price improvement (difference between executed and quote)
    2. Limit price improvement (surplus)

    It includes cases where surplus is smaller than quote price improvement,
    which should result in the surplus value being returned.
    """
    trade = Mock(spec=OnchainTrade)
    trade.sell_amount = sell_amount
    trade.buy_amount = buy_amount
    trade.kind = kind
    # Mock surplus to return the specified value
    trade.surplus = Mock(return_value=surplus_value)

    quote = Quote(
        sell_amount=quote_sell_amount,
        buy_amount=quote_buy_amount,
        fee_amount=quote_fee_amount,
    )

    assert OnchainTrade.price_improvement(trade, quote) == expected_improvement


@pytest.mark.parametrize(
    "kind,amount_field,amount_with_fee,amount_without_fee,volume_factor",
    [
        # sell order (fee affects buy_amount)
        ("sell", "buy_amount", 6000 - 600, 6000, Fraction(0.1)),
        # buy order (fee affects sell_amount)
        ("buy", "sell_amount", 50 + 5, 50, Fraction(0.1)),
    ],
)
def test_volume_protocol_fee(
    kind, amount_field, amount_with_fee, amount_without_fee, volume_factor
):
    """Test volume-based protocol fee calculation for different order kinds."""
    # Create trade with fee applied
    trade = MagicMock(spec=OffchainTrade)
    setattr(trade, amount_field, amount_with_fee)
    trade.volume = Mock(return_value=getattr(trade, amount_field))
    trade.kind = kind

    # Reverse the fee application
    new_trade = VolumeFeePolicy(volume_factor).reverse_protocol_fee(trade)

    # Verify the amount without fee
    assert getattr(new_trade, amount_field) == amount_without_fee


@pytest.mark.parametrize(
    "kind,amount_field,is_capped,surplus_factor,volume_factor,expected_formula",
    [
        # Not capped cases (surplus fee < volume fee)
        # sell order - not capped
        (
            "sell",
            "buy_amount",
            False,
            Fraction(0.5),
            Fraction(0.5),
            lambda amount, surplus, s_factor, v_factor: amount
            + round(s_factor / (1 - s_factor) * surplus),
        ),
        # buy order - not capped
        (
            "buy",
            "sell_amount",
            False,
            Fraction(0.5),
            Fraction(0.5),
            lambda amount, surplus, s_factor, v_factor: amount
            - round(s_factor / (1 - s_factor) * surplus),
        ),
        # Capped cases (surplus fee > volume fee)
        # sell order - capped
        (
            "sell",
            "buy_amount",
            True,
            Fraction(0.5),
            Fraction(0.01),
            lambda amount, surplus, s_factor, v_factor: amount
            + round(v_factor / (1 - v_factor) * amount),
        ),
        # buy order - capped
        (
            "buy",
            "sell_amount",
            True,
            Fraction(0.5),
            Fraction(0.01),
            lambda amount, surplus, s_factor, v_factor: amount
            - round(v_factor / (1 + v_factor) * amount),
        ),
    ],
)
def test_surplus_protocol_fee(
    kind, amount_field, is_capped, surplus_factor, volume_factor, expected_formula
):
    """Test surplus-based protocol fee calculation for different order kinds and capping scenarios."""
    amount = 15 * 10**18
    surplus = 5 * 10**18

    # Create trade with fee applied
    trade = Mock(spec=OffchainTrade)
    setattr(trade, amount_field, amount)
    trade.kind = kind
    trade.volume = Mock(return_value=amount)
    trade.surplus = Mock(return_value=surplus)

    # Reverse the fee application
    new_trade = SurplusFeePolicy(surplus_factor, volume_factor).reverse_protocol_fee(
        trade
    )

    # Verify the amount without fee
    expected_amount = expected_formula(amount, surplus, surplus_factor, volume_factor)
    assert getattr(new_trade, amount_field) == expected_amount


@pytest.mark.parametrize(
    "kind,amount_field,price_improvement_value,surplus_value,is_capped,price_improvement_factor,volume_factor,expected_formula",
    [
        # Not capped cases (price improvement fee < volume fee)
        # sell order - not capped
        (
            "sell",
            "buy_amount",
            5 * 10**18,  # positive price improvement
            5 * 10**18,  # surplus equals price improvement
            False,
            Fraction(0.5),
            Fraction(0.5),
            lambda amount, pi, pi_factor, v_factor: amount
            + round(pi_factor / (1 - pi_factor) * pi),
        ),
        # buy order - not capped
        (
            "buy",
            "sell_amount",
            5 * 10**18,  # positive price improvement
            5 * 10**18,  # surplus equals price improvement
            False,
            Fraction(0.5),
            Fraction(0.5),
            lambda amount, pi, pi_factor, v_factor: amount
            - round(pi_factor / (1 - pi_factor) * pi),
        ),
        # Capped cases (price improvement fee > volume fee)
        # sell order - capped
        (
            "sell",
            "buy_amount",
            5 * 10**18,  # positive price improvement
            5 * 10**18,  # surplus equals price improvement
            True,
            Fraction(0.5),
            Fraction(0.01),
            lambda amount, pi, pi_factor, v_factor: amount
            + round(v_factor / (1 - v_factor) * amount),
        ),
        # buy order - capped
        (
            "buy",
            "sell_amount",
            5 * 10**18,  # positive price improvement
            5 * 10**18,  # surplus equals price improvement
            True,
            Fraction(0.5),
            Fraction(0.01),
            lambda amount, pi, pi_factor, v_factor: amount
            - round(v_factor / (1 + v_factor) * amount),
        ),
        # Negative price improvement cases
        # sell order - negative price improvement
        (
            "sell",
            "buy_amount",
            -5 * 10**18,  # negative price improvement
            -5 * 10**18,  # surplus equals price improvement
            False,
            Fraction(0.5),
            Fraction(0.01),
            lambda amount, pi, pi_factor, v_factor: amount,  # No change
        ),
        # buy order - negative price improvement
        (
            "buy",
            "sell_amount",
            -5 * 10**18,  # negative price improvement
            -5 * 10**18,  # surplus equals price improvement
            False,
            Fraction(0.5),
            Fraction(0.01),
            lambda amount, pi, pi_factor, v_factor: amount,  # No change
        ),
        # Cases where surplus is smaller than price improvement
        # sell order - surplus (1) < price improvement (2)
        (
            "sell",
            "buy_amount",
            2 * 10**18,  # quote price improvement
            1 * 10**18,  # surplus (smaller)
            False,
            Fraction(0.5),
            Fraction(0.5),
            lambda amount, pi, pi_factor, v_factor: amount
            + round(pi_factor / (1 - pi_factor) * (1 * 10**18)),  # Use surplus value
        ),
        # buy order - surplus (1) < price improvement (2)
        (
            "buy",
            "sell_amount",
            2 * 10**18,  # quote price improvement
            1 * 10**18,  # surplus (smaller)
            False,
            Fraction(0.5),
            Fraction(0.5),
            lambda amount, pi, pi_factor, v_factor: amount
            - round(pi_factor / (1 - pi_factor) * (1 * 10**18)),  # Use surplus value
        ),
        # Edge case: sell order with zero surplus (0) < price improvement (5)
        (
            "sell",
            "buy_amount",
            5 * 10**18,  # quote price improvement
            0,  # zero surplus
            False,
            Fraction(0.5),
            Fraction(0.5),
            lambda amount, pi, pi_factor, v_factor: amount,  # No fee applied
        ),
    ],
)
def test_price_improvement_protocol_fee(
    kind,
    amount_field,
    price_improvement_value,
    surplus_value,
    is_capped,
    price_improvement_factor,
    volume_factor,
    expected_formula,
):
    """Test price improvement-based protocol fee calculation for different scenarios.

    Tests:
    1. Not capped cases - where price improvement fee is less than volume fee
    2. Capped cases - where price improvement fee is greater than volume fee
    3. Negative price improvement cases - where no fee is applied
    4. Cases where surplus is smaller than quote price improvement - should use the smaller value
    5. Edge case with zero surplus - should apply no fee
    """
    amount = 15 * 10**18

    # Create mock quote
    quote = Mock(spec=Quote)

    # Create fee policy
    fee_policy = PriceImprovementFeePolicy(
        price_improvement_factor,
        volume_factor,
        quote,
    )

    # Create trade with fee applied
    trade = Mock(spec=OffchainTrade)
    setattr(trade, amount_field, amount)
    trade.kind = kind
    trade.volume = Mock(return_value=amount)

    # Set up price_improvement to return the minimum of quote price improvement and surplus
    # This matches the actual behavior of the price_improvement method
    min_improvement = min(price_improvement_value, surplus_value)
    trade.price_improvement = Mock(return_value=min_improvement)

    # Set up surplus to return the specified surplus value
    trade.surplus = Mock(return_value=surplus_value)

    # Reverse the fee application
    new_trade = fee_policy.reverse_protocol_fee(trade)

    # Verify the amount without fee
    # Use the minimum improvement value in the expected formula
    min_improvement = min(price_improvement_value, surplus_value)
    expected_amount = expected_formula(
        amount, min_improvement, price_improvement_factor, volume_factor
    )
    assert getattr(new_trade, amount_field) == expected_amount
