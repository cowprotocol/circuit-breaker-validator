"""
Various definitions.
"""

from dataclasses import dataclass, field
from fractions import Fraction
import math

from hexbytes import HexBytes


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
        order_hooks: Dict mapping order_uid to Hooks for that order.
            May contain entries for orders not in this settlement without causing issues.
    """

    auction_id: int
    # solution data
    solver: HexBytes
    trades: list[OffchainTrade]
    order_hooks: dict[HexBytes, Hooks]
