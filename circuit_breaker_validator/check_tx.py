"""
Class to run tests on a transaction.
"""

# pylint: disable=logging-fstring-interpolation

from hexbytes import HexBytes

from circuit_breaker_validator.exceptions import InvalidSettlement
from circuit_breaker_validator.logger import logger
from circuit_breaker_validator.models import (
    OffchainSettlementData,
    OnchainSettlementData,
    OffchainTrade,
    Hook,
    Hooks,
)
from circuit_breaker_validator.scores import compute_score

SCORE_CHECK_THRESHOLD = 10**12


def inspect(
    onchain_data: OnchainSettlementData,
    offchain_data: OffchainSettlementData,
) -> None:
    """Method that runs multiple tests given on-chain and off-chain data
    If the test fails it raises an InvalidSettlement exception.
    """
    logger.info(f"Checking auction with id {onchain_data.auction_id}")

    checks = [check_solver, check_orders, check_score, check_hooks]
    results = [check(onchain_data, offchain_data) for check in checks]

    result = all(results)
    if result:
        logger.info("Auction passed all checks.")
    else:
        raise InvalidSettlement(
            "Invalid settlement: "
            f"id {onchain_data.auction_id}\t solver {onchain_data.solver!r} test results {results}",
            solver=onchain_data.solver,
        )


def check_solver(
    onchain_data: OnchainSettlementData,
    offchain_data: OffchainSettlementData,
) -> bool:
    """Check that the settlement was submitted by the winning solver"""
    if onchain_data.solver != offchain_data.solver:
        logger.error(
            f"Transaction hash {onchain_data.tx_hash!r}: "
            "Settlement not executed by winning solver. "
            f"Solver on-chain: {onchain_data.solver!r}\t"
            f"Solver off-chain: {offchain_data.solver!r}"
        )
        return False
    return True


def check_orders(
    onchain_data: OnchainSettlementData,
    offchain_data: OffchainSettlementData,
) -> bool:
    """Check orders of the settlement

    Performs three validation checks in order:
    1. 1-to-1 mapping between executed and proposed trades
       - All executed trades must have been proposed in the bid
       - All JIT orders must be revealed in the bidding phase
    2. Executed amounts match proposed amounts
       - Sell and buy amounts must match exactly between on-chain and off-chain
    3. Surplus validation for non-standard orders
       - Orders with non-zero surplus either:
         - were part of the auction (normal order), OR
         - have a surplus capturing jit order owner (cow amm order)
    """
    onchain_trades_dict = {trade.order_uid: trade for trade in onchain_data.trades}
    offchain_trades_dict = {trade.order_uid: trade for trade in offchain_data.trades}

    # Check 1: 1-to-1 mapping between executed and proposed trades
    if onchain_trades_dict.keys() != offchain_trades_dict.keys():
        logger.error(
            f"Transaction hash {onchain_data.tx_hash!r}: "
            f"Trades mismatch. On-chain: {len(onchain_trades_dict)}, "
            f"Off-chain: {len(offchain_trades_dict)}"
        )
        return False

    # Check 2: executed amounts match proposed amounts
    for order_uid, offchain_trade in offchain_trades_dict.items():
        onchain_trade = onchain_trades_dict[order_uid]
        if (
            onchain_trade.sell_amount != offchain_trade.sell_amount
            or onchain_trade.buy_amount != offchain_trade.buy_amount
        ):
            logger.error(
                f"Transaction hash {onchain_data.tx_hash!r}: "
                "Executed trades do not match revealed trades."
            )
            logger.error(
                f"On-chain trade:  {onchain_trade}\t"
                f"Off-chain trade: {offchain_trade}"
            )
            return False

    # Check 3: surplus validation for non-standard orders
    for order_uid, onchain_trade in onchain_trades_dict.items():
        if onchain_trade.surplus() > 0:
            if (
                order_uid not in offchain_data.valid_orders
                and onchain_trade.owner not in offchain_data.jit_order_addresses
            ):
                logger.error(
                    f"Transaction hash {onchain_data.tx_hash!r}: "
                    f"Non-CoW AMM JIT order with non-zero surplus: {order_uid!r}"
                )
                return False

    return True


def check_score(
    onchain_data: OnchainSettlementData,
    offchain_data: OffchainSettlementData,
) -> bool:
    """Check if the score of the settlement equals revealed score
    The tolerance of 100 (atoms) is probably due to different rounding in this code
    compared to the driver/autopilot"""
    computed_score = compute_score(onchain_data, offchain_data)
    competition_score = offchain_data.score
    logger.debug(
        f"Score in competition: {competition_score}\tComputed score: {computed_score}\t"
        f"Difference {competition_score - computed_score}"
    )
    if competition_score - computed_score > SCORE_CHECK_THRESHOLD:
        logger.error(
            f"Transaction hash {onchain_data.tx_hash!r}: "
            "Computed score smaller than score reported in competition."
        )
        logger.warning(
            f"Score in competition: {competition_score}\tComputed score: {computed_score}\t"
            f"Difference {competition_score - computed_score}"
        )
        return False
    return True


def _check_hook_execution(
    onchain_data: OnchainSettlementData,
    order_uid: HexBytes,
    hook: Hook,
    hook_type: str,
) -> bool:
    """Helper function to check if a hook was executed properly

    Args:
        onchain_data: On-chain settlement data
        order_uid: Order UID
        hook: Hook to check
        hook_type: Type of hook ("pre" or "post")

    Returns:
        True if hook was executed properly, False otherwise
    """
    # Select the appropriate list of candidates based on hook_type
    if hook_type == "pre":
        candidates = onchain_data.hook_candidates.pre_hooks
    else:  # hook_type == "post"
        candidates = onchain_data.hook_candidates.post_hooks

    hook_executed = False
    for hook_candidate in candidates:
        if (
            hook_candidate.target == hook.target
            and hook_candidate.calldata == hook.calldata
        ):
            # Check gas limit (rule 4d) that it's >= the required gas limit
            if (
                hook_candidate.gas_limit != 0
                and hook_candidate.gas_limit < hook.gas_limit
            ):
                logger.error(
                    f"Transaction hash {onchain_data.tx_hash!r}: "
                    f"{hook_type.capitalize()}-hook for order {order_uid!r} has insufficient gas. "
                    f"Required: {hook.gas_limit}, "
                    f"Provided: {hook_candidate.gas_limit}. "
                    f"Hook: target={hook.target!r}, "
                    f"calldata={hook.calldata!r}"
                )
                return False
            hook_executed = True
            break

    if not hook_executed:
        logger.error(
            f"Transaction hash {onchain_data.tx_hash!r}: "
            f"{hook_type.capitalize()}-hook not executed for order {order_uid!r}. "
            f"Hook: target={hook.target!r}, calldata={hook.calldata!r}"
        )
        return False

    return True


def _has_hooks(offchain_data: OffchainSettlementData) -> bool:
    """Check if there are any hooks defined in the offchain data.

    Args:
        offchain_data: Off-chain settlement data

    Returns:
        True if there are hooks defined, False otherwise
    """
    # If there are no order_hooks, return False
    if not offchain_data.order_hooks:
        return False

    # Check if any order has hooks defined
    for _, hooks in offchain_data.order_hooks.items():
        if hooks.pre_hooks or hooks.post_hooks:
            return True

    # No hooks found
    return False


def _find_offchain_trade(
    offchain_data: OffchainSettlementData, order_uid: HexBytes
) -> OffchainTrade:
    """Find the corresponding offchain trade for an order UID.

    Args:
        offchain_data: Off-chain settlement data
        order_uid: Order UID to find

    Returns:
        The corresponding offchain trade, or raises ValueError if not found
    """
    for trade in offchain_data.trades:
        if trade.order_uid == order_uid:
            return trade
    raise ValueError(f"Order UID {order_uid!r} not found in offchain trades")


def _check_order_hooks(
    onchain_data: OnchainSettlementData,
    offchain_data: OffchainSettlementData,
    order_uid: HexBytes,
    hooks: Hooks,
) -> bool:
    """Check hooks for a specific order.

    Args:
        onchain_data: On-chain settlement data
        offchain_data: Off-chain settlement data
        order_uid: Order UID
        hooks: Hooks for the order

    Returns:
        True if all required hooks were executed properly, False otherwise
    """
    # Find the corresponding offchain trade to check its executed field
    offchain_trade = _find_offchain_trade(offchain_data, order_uid)

    # For pre-hooks, we need to check if this is the first fill (executed = 0)
    # Pre-hooks should only be executed on the first fill
    is_first_fill = offchain_trade.already_executed_amount == 0

    # If there are hooks in the offchain data and its the first fill,
    # but there aren't hook candidates in onchain data return False
    has_no_hook_candidates = (
        not onchain_data.hook_candidates.pre_hooks
        and not onchain_data.hook_candidates.post_hooks
    )
    if has_no_hook_candidates and is_first_fill:
        return False

    # Check pre-hooks (only for the first fill)
    if is_first_fill:
        for pre_hook in hooks.pre_hooks:
            if not _check_hook_execution(onchain_data, order_uid, pre_hook, "pre"):
                return False
    else:
        # For subsequent fills, ensure pre-hooks are NOT executed
        if hooks.pre_hooks and onchain_data.hook_candidates.pre_hooks:
            # Check if any of the required pre-hooks are present in the executed hooks
            for pre_hook in hooks.pre_hooks:
                for executed_hook in onchain_data.hook_candidates.pre_hooks:
                    if (
                        executed_hook.target == pre_hook.target
                        and executed_hook.calldata == pre_hook.calldata
                    ):
                        logger.error(
                            f"Transaction hash {onchain_data.tx_hash!r}: "
                            f"Pre-hook incorrectly executed for "
                            f"subsequent fill of order {order_uid!r}. "
                            f"Pre-hooks should only be executed on first fill. "
                            f"Hook: target={pre_hook.target!r}, calldata={pre_hook.calldata!r}"
                        )
                        return False

    # Check post-hooks (always required, even for partially filled orders)
    for post_hook in hooks.post_hooks:
        if not _check_hook_execution(onchain_data, order_uid, post_hook, "post"):
            return False

    return True


def check_hooks(
    onchain_data: OnchainSettlementData,
    offchain_data: OffchainSettlementData,
) -> bool:
    """Check if hooks were executed correctly according to the rules.

    Hook Validation Rules:
    1. Pre-hooks need to be executed before pulling in user funds
       - Guaranteed by: OnchainSettlementData.hook_candidates being populated with pre-hooks
         appearing before trade executions in the transaction trace
       - Not explicitly checked in this function

    2. Post-hooks need to be executed after pushing out user order proceeds
       - Guaranteed by: OnchainSettlementData.hook_candidates being populated with post-hooks
         appearing after trade executions in the transaction trace
       - Not explicitly checked in this function

    3. Partially fillable orders:
       a. Should execute the pre-hooks on the first fill only
          - Explicitly checked: Validated by checking
          offchain_trade.already_executed_amount == 0 (lines 264, 272-275)
       b. Should execute the post-hooks on every fill
          - Explicitly checked: Post-hooks are always
          validated regardless of fill status (lines 277-280)

    4. Execution of a hook means:
       a. There exists an internal CALL in the settlement transaction with a matching triplet:
          target, gasLimit, calldata
          - Partially checked: target and calldata are checked for exact match (lines 170-173)
          - Gas limit is validated as >= required, with 0 meaning unlimited (lines 176-187)

       b. The hook needs to be attempted, meaning the hook reverting is not violating any rules
          - NOT IMPLEMENTED: This requires transaction trace analysis to determine if the hook
            was attempted. Future implementation may require extending Hook data structure with
            an 'attempted' attribute.

       c. Intermediate calls between the call to settle and hook execution must not revert
          - NOT IMPLEMENTED: This requires transaction trace analysis to track call stack state.
            Future implementation may require extending Hook data structure with an attribute
            like 'no_upstream_revert' to indicate this
            validation was performed during data fetching.

       d. The available gas forwarded to the hook CALL is greater or equal than specified gasLimit
          - Explicitly checked: Validated that gas_limit
          (if non-zero) is >= required (lines 176-187)

    Args:
        onchain_data: On-chain settlement data containing hook_candidates from transaction trace
        offchain_data: Off-chain settlement data containing expected hooks from order appData

    Returns:
        True if all required hooks were found and validated successfully, False otherwise
    """
    # Check if there are any hooks defined
    has_hooks = _has_hooks(offchain_data)

    # If no hooks are defined, return True
    if not has_hooks:
        return True

    # Check hooks for each order
    for order_uid, hooks in offchain_data.order_hooks.items():
        if not _check_order_hooks(onchain_data, offchain_data, order_uid, hooks):
            return False

    return True
