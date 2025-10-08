"""Functionality to compute scores"""

from fractions import Fraction

from circuit_breaker_validator.models import (
    OffchainSettlementData,
    OnchainSettlementData,
)

NATIVE_TOKEN_PRICE = 10**18


def compute_score(
    onchain_data: OnchainSettlementData,
    offchain_data: OffchainSettlementData,
) -> int:
    """Compute the score of a solution by summing the raw surplus value of all trades.

    The score calculation process:
    1. For each trade, calculate the raw surplus using trade fee policies
    2. Convert the surplus to the buy token denomination using the limit price
    3. Convert the surplus, expressed in the buy token, to ETH using native token prices
    4. Round the ETH value and add it to the total score

    This score represents the total value (in native token atoms) created by the solution.

    Args:
        onchain_data: Settlement data from the blockchain
        offchain_data: Settlement data from the orderbook

    Returns:
        int: The total score in ETH wei
    """
    score = 0
    for trade in onchain_data.trades:
        raw_surplus = trade.raw_surplus(
            offchain_data.trade_fee_policies.get(trade.order_uid, [])
        )
        # conversion to buy token using limit price
        if trade.surplus_token() == trade.sell_token:
            raw_surplus_buy_token = raw_surplus * Fraction(
                trade.limit_buy_amount, trade.limit_sell_amount
            )
        else:
            raw_surplus_buy_token = Fraction(raw_surplus)
        # conversion to ETH
        raw_surplus_eth = raw_surplus_buy_token * Fraction(
            offchain_data.native_prices[trade.buy_token], NATIVE_TOKEN_PRICE
        )
        score += round(raw_surplus_eth)
    return score
