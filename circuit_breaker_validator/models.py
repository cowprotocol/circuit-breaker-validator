"""
Various definitions.
"""

from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass, field
from fractions import Fraction
import math

from hexbytes import HexBytes


@dataclass
class Quote:
    """Class representing quotes"""

    sell_amount: int
    buy_amount: int
    fee_amount: int

    def effective_sell_amount(self, kind: str) -> int:
        """Compute effective sell amount accounting for fees.

        For sell orders, this is simply the sell_amount.
        For buy orders, this includes both sell_amount and fee_amount.

        This calculation determines the total amount of tokens the user is sending,
        including any fees that might be charged.
        """
        if kind == "sell":
            return self.sell_amount
        if kind == "buy":
            return self.sell_amount + self.fee_amount
        raise ValueError(f"Order kind {kind} is invalid.")

    def effective_buy_amount(self, kind: str) -> int:
        """Compute effective buy amount accounting for fees.

        For sell orders, this calculates how many buy tokens the user will receive after fees,
        using the exchange rate and applying fees to the sell amount.
        For buy orders, this is simply the buy_amount.

        This calculation determines the actual amount of tokens the user will receive,
        taking into account any fees that might reduce the effective amount.
        """
        if kind == "sell":
            exchange_rate = Fraction(self.buy_amount, self.sell_amount)
            return math.ceil((self.sell_amount - self.fee_amount) * exchange_rate)
        if kind == "buy":
            return self.buy_amount
        raise ValueError(f"Order kind {kind} is invalid.")


@dataclass
class Hook:
    """Class to describe a hook.

    A hook represents a contract call that should be executed as part of an order settlement.
    This class contains the essential information needed to identify and validate hook execution.
    """

    target: HexBytes
    calldata: HexBytes
    gas_limit: int


@dataclass
class Hooks:
    """Class to describe hooks for an order"""

    pre_hooks: list[Hook] = field(default_factory=list)
    post_hooks: list[Hook] = field(default_factory=list)


@dataclass
class Trade:
    """Base class for trades"""

    order_uid: HexBytes
    sell_amount: int
    buy_amount: int


@dataclass
class OnchainTrade(Trade):
    """Class to describe onchain info about a trade
    This information can be computed from calldata of a settlement.
    """

    owner: HexBytes
    sell_token: HexBytes
    buy_token: HexBytes
    limit_sell_amount: int
    limit_buy_amount: int
    kind: str

    def volume(self) -> int:
        """Compute volume of a trade in the surplus token"""
        if self.kind == "sell":
            return self.buy_amount
        if self.kind == "buy":
            return self.sell_amount
        raise ValueError(f"Order kind {self.kind} is invalid.")

    def surplus(self) -> int:
        """Compute surplus of a trade in the surplus token.

        Surplus represents the benefit gained by the trader compared to the limit price.
        For sell orders: surplus = executed_buy_amount - limit_buy_amount (extra tokens received)
        For buy orders: surplus = limit_sell_amount - executed_sell_amount (tokens saved)

        For partially fillable orders, rounding is such that the reference for computing surplus is
        such that it gives the worst price still allowed by the smart contract. That means that for
        sell orders the limit buy amount is rounded up and for buy orders the limit sell amount is
        rounded down.

        https://github.com/cowprotocol/contracts/blob/39d7f4d68e37d14adeaf3c0caca30ea5c1a2fad9/src/contracts/GPv2Settlement.sol#L337
        """
        if self.kind == "sell":
            current_limit_buy_amount = math.ceil(
                self.limit_buy_amount
                * Fraction(self.sell_amount, self.limit_sell_amount)
            )
            return self.buy_amount - current_limit_buy_amount
        if self.kind == "buy":
            current_limit_sell_amount = int(
                self.limit_sell_amount
                * Fraction(self.buy_amount, self.limit_buy_amount)
            )
            return current_limit_sell_amount - self.sell_amount
        raise ValueError(f"Order kind {self.kind} is invalid.")

    def raw_surplus(self, fee_policies: list["FeePolicy"]) -> int:
        """Compute raw surplus of a trade in the surplus token.

        Raw surplus represents the total benefit before protocol fees were applied.
        The calculation works by:
        1. Creating a copy of the current trade
        2. Reversing all protocol fees that were applied (in reverse order)
        3. Computing the surplus of the resulting trade

        This gives us the "true" surplus that would have existed without protocol fees.
        """
        raw_trade = deepcopy(self)
        for fee_policy in reversed(fee_policies):
            raw_trade = fee_policy.reverse_protocol_fee(raw_trade)
        return raw_trade.surplus()

    def protocol_fee(self, fee_policies: list["FeePolicy"]) -> int:
        """Compute protocol fees of a trade in the surplus token
        Protocol fees are computed as the difference of raw surplus and surplus."""

        return self.raw_surplus(fee_policies) - self.surplus()

    def surplus_token(self) -> HexBytes:
        """Returns the surplus token"""
        if self.kind == "sell":
            return self.buy_token
        if self.kind == "buy":
            return self.sell_token
        raise ValueError(f"Order kind {self.kind} is invalid.")

    def price_improvement(self, quote: Quote) -> int:
        """Compute price improvement compared to a reference quote and limit price.

        Price improvement measures how much better the executed trade is compared to the better
        of quote and limit price. The smaller improvement value is used, as that results in a
        smaller fee.

        For sell orders: price_improvement =
            executed_buy_amount - max(buy_amount_from_quote, limit_buy_amount)
        For buy orders: price_improvement =
            min(sell_amount_from_quote, limit_sell_amount) - executed_sell_amount

        The calculation uses the effective amounts from the quote that account for gas fees:
        1. Get effective sell and buy amounts from the quote
        2. Compare the actual trade to the hypothetical quote-based trade
        3. Compare with the limit price (surplus)
        4. Return the minimum of the two improvements

        For partially fillable orders, rounding is such that the reference for computing price
        improvement is as if the quote would determine the limit price. That means that for sell
        orders the quote buy amount is rounded up and for buy orders the quote sell amount is
        rounded down.
        """
        # Calculate price improvement compared to quote
        effective_sell_amount = quote.effective_sell_amount(self.kind)
        effective_buy_amount = quote.effective_buy_amount(self.kind)
        if self.kind == "sell":
            current_limit_quote_amount = math.ceil(
                effective_buy_amount * Fraction(self.sell_amount, effective_sell_amount)
            )
            quote_price_improvement = self.buy_amount - current_limit_quote_amount
        elif self.kind == "buy":
            current_quote_sell_amount = int(
                effective_sell_amount * Fraction(self.buy_amount, effective_buy_amount)
            )
            quote_price_improvement = current_quote_sell_amount - self.sell_amount
        else:
            raise ValueError(f"Order kind {self.kind} is invalid.")

        # Calculate price improvement compared to limit price (surplus)
        limit_price_improvement = self.surplus()

        # Return the minimum of the two improvements
        # "Better" means smaller improvement, as that results in a smaller fee
        return min(quote_price_improvement, limit_price_improvement)


class FeePolicy(ABC):
    """Abstract class for protocol fees
    Concrete implementations have to implement a reverse_protocol_fee method.
    """

    # pylint: disable=too-few-public-methods

    @abstractmethod
    def reverse_protocol_fee(self, trade: OnchainTrade) -> OnchainTrade:
        """Reverse application of protocol fee
        Returns a new trade object
        """


@dataclass
class OffchainTrade(Trade):
    """Class to describe offchain info about a trade."""

    # This value represent how much the order was executed before the settlement.
    # If the order is executed twice in the same settlement, value will be the same for both.
    # 0 means it's the first fill, any other value means it's not
    already_executed_amount: int


@dataclass
class OnchainSettlementData:
    """Class to describe onchain info about a settlement.

    Attributes:
        auction_id: Unique identifier for the auction
        tx_hash: Transaction hash of the settlement
        solver: Address of the solver that submitted the settlement
        trades: List of trades executed in this settlement
        hook_candidates: Hooks structure containing pre-hooks and post-hooks extracted from
            transaction trace.
            - The ordering in each list reflects the actual execution order in the transaction
            - Each Hook contains the target address, calldata, and gas_limit from the actual call
    """

    auction_id: int
    tx_hash: HexBytes
    solver: HexBytes
    trades: list[OnchainTrade]
    hook_candidates: Hooks


@dataclass
class OffchainSettlementData:
    """Class to describe offchain info about a settlement.

    Attributes:
        auction_id: Unique identifier for the auction
        solver: Address of the solver that submitted the settlement
        trades: List of trades proposed in the settlement
        score: The score of the settlement as reported in the competition
        trade_fee_policies: Dict mapping order_uid to list of fee policies for that order.
            May contain entries for orders not in this settlement without causing issues.
        valid_orders: Set of order_uids that were valid in the auction
        jit_order_addresses: Set of addresses that are JIT order owners
        native_prices: Dict mapping token addresses to their native prices
        order_hooks: Dict mapping order_uid to Hooks for that order.
            May contain entries for orders not in this settlement without causing issues.
    """

    # pylint: disable=too-many-instance-attributes

    auction_id: int
    # solution data
    solver: HexBytes
    trades: list[OffchainTrade]
    score: int
    # auction data
    trade_fee_policies: dict[HexBytes, list[FeePolicy]]
    valid_orders: set[HexBytes]
    jit_order_addresses: set[HexBytes]
    native_prices: dict[HexBytes, int]
    order_hooks: dict[HexBytes, Hooks]


@dataclass
class VolumeFeePolicy(FeePolicy):
    """Volume based protocol fee"""

    volume_factor: Fraction

    def reverse_protocol_fee(self, trade: OnchainTrade) -> OnchainTrade:
        """Reverse the volume-based protocol fee to get the pre-fee trade.

        This method calculates what the trade would have been before volume-based fee was applied:
        1. For sell orders: Increases the buy_amount by adding back the fee that was taken
        2. For buy orders: Decreases the sell_amount by removing the fee that was added

        The fee calculation uses the volume_factor parameter:
        - For sell orders: fee = volume * volume_factor / (1 - volume_factor)
        - For buy orders: fee = volume * volume_factor / (1 + volume_factor)

        Returns a new trade object with the fee reversed.
        """
        new_trade = deepcopy(trade)
        volume = trade.volume()
        if trade.kind == "sell":
            fee = round(volume * self.volume_factor / (1 - self.volume_factor))
            new_trade.buy_amount = trade.buy_amount + fee
        elif trade.kind == "buy":
            fee = round(volume * self.volume_factor / (1 + self.volume_factor))
            new_trade.sell_amount = trade.sell_amount - fee
        else:
            raise ValueError(f"Order kind {trade.kind} is invalid.")
        return new_trade


@dataclass
class SurplusFeePolicy(FeePolicy):
    """Surplus based protocol fee"""

    surplus_factor: Fraction
    surplus_max_volume_factor: Fraction

    def reverse_protocol_fee(self, trade: OnchainTrade) -> OnchainTrade:
        """Reverse the surplus-based protocol fee to get the pre-fee trade.

        This method calculates what the trade would have been before surplus-based fee was applied:
        1. Calculate the surplus fee based on the current surplus and surplus_factor
        2. Calculate a maximum volume-based fee using surplus_max_volume_factor
        3. Take the minimum of these two fees to determine the actual fee
        4. For sell orders: Increase buy_amount by adding back the fee
        5. For buy orders: Decrease sell_amount by removing the fee

        The fee calculations use:
        - surplus_fee = surplus * surplus_factor / (1 - surplus_factor)
        - volume_fee = volume * surplus_max_volume_factor / (1 ± surplus_max_volume_factor)
          (+ for buy orders, - for sell orders)

        Returns a new trade object with the fee reversed.
        """
        new_trade = deepcopy(trade)
        surplus = trade.surplus()
        volume = trade.volume()
        surplus_fee = round(surplus * self.surplus_factor / (1 - self.surplus_factor))
        if trade.kind == "sell":
            volume_fee = round(
                volume
                * self.surplus_max_volume_factor
                / (1 - self.surplus_max_volume_factor)
            )
            fee = min(surplus_fee, volume_fee)
            new_trade.buy_amount = trade.buy_amount + fee
        elif trade.kind == "buy":
            volume_fee = round(
                volume
                * self.surplus_max_volume_factor
                / (1 + self.surplus_max_volume_factor)
            )
            fee = min(surplus_fee, volume_fee)
            new_trade.sell_amount = trade.sell_amount - fee
        else:
            raise ValueError(f"Order kind {trade.kind} is invalid.")
        return new_trade


@dataclass
class PriceImprovementFeePolicy(FeePolicy):
    """Price improvement based protocol fee"""

    price_improvement_factor: Fraction
    price_improvement_max_volume_factor: Fraction
    quote: Quote

    def reverse_protocol_fee(self, trade: OnchainTrade) -> OnchainTrade:
        """Reverse the price improvement-based protocol fee to get the pre-fee trade.

        This method calculates what the trade would have been before improvement fee was applied:
        1. Calculate the price improvement compared to the reference quote
        2. Calculate the price improvement fee based on price_improvement_factor
        3. Calculate a maximum volume-based fee using price_improvement_max_volume_factor
        4. Take the minimum of these two fees to determine the actual fee
        5. For sell orders: Increase buy_amount by adding back the fee
        6. For buy orders: Decrease sell_amount by removing the fee

        The fee calculations use:
        - price_improvement_fee = price_improvement * price_improvement_factor /
            (1 - price_improvement_factor)
        - volume_fee = volume * price_improvement_max_volume_factor /
            (1 ± price_improvement_max_volume_factor)
          (+ for buy orders, - for sell orders)

        Returns a new trade object with the fee reversed.
        """
        new_trade = deepcopy(trade)

        # Calculate price improvement compared to quote
        price_improvement = trade.price_improvement(self.quote)
        volume = trade.volume()
        price_improvement_fee = max(
            0,
            round(
                price_improvement
                * self.price_improvement_factor
                / (1 - self.price_improvement_factor)
            ),
        )
        if trade.kind == "sell":
            volume_fee = round(
                volume
                * self.price_improvement_max_volume_factor
                / (1 - self.price_improvement_max_volume_factor)
            )
            fee = min(price_improvement_fee, volume_fee)
            new_trade.buy_amount = trade.buy_amount + fee
        elif trade.kind == "buy":
            volume_fee = round(
                volume
                * self.price_improvement_max_volume_factor
                / (1 + self.price_improvement_max_volume_factor)
            )
            fee = min(price_improvement_fee, volume_fee)
            new_trade.sell_amount = trade.sell_amount - fee
        else:
            raise ValueError(f"Order kind {trade.kind} is invalid.")
        return new_trade
