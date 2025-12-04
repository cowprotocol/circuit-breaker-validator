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


def _check_hook_execution(hook: Hook, hook_candidates: list[Hook]) -> bool:
    """Helper function to check if a hook was executed properly

    Args:
        hook: Hook to check
        hook_candidates: List of hook candidates from onchain execution

    Returns:
        True if hook was found in candidates, False otherwise
    """
    for hook_candidate in hook_candidates:
        if (
            hook_candidate.target == hook.target
            and hook_candidate.calldata == hook.calldata
            and hook_candidate.gas_limit == hook.gas_limit
        ):
            return True
    return False


def _check_order_hooks(
    tx_hash: HexBytes,
    trade: OffchainTrade,
    hooks: Hooks,
    hook_candidates: Hooks,
) -> bool:
    """Check hooks for a specific trade.

    Args:
        tx_hash: Transaction hash for logging
        trade: The trade to check hooks for
        hooks: Expected hooks for the trade
        hook_candidates: Hook candidates extracted from onchain execution

    Returns:
        True if all required hooks were executed properly, False otherwise
    """
    # If there are no hooks defined for this trade, validation passes
    if not hooks.pre_hooks and not hooks.post_hooks:
        return True

    # For pre-hooks, we need to check if this is the first fill
    # Pre-hooks should only be executed on the first fill
    is_first_fill = trade.already_executed_amount == 0

    # If there are hooks in the offchain data and it's the first fill,
    # but there aren't hook candidates in onchain data, return False
    has_no_hook_candidates = (
        not hook_candidates.pre_hooks and not hook_candidates.post_hooks
    )
    if has_no_hook_candidates and is_first_fill:
        logger.error(
            f"Transaction hash {tx_hash!r}: "
            f"Hooks defined for order {trade.order_uid!r} "
            f"but no hook candidates found in transaction"
        )
        return False

    # Check pre-hooks (only for the first fill)
    if is_first_fill:
        for pre_hook in hooks.pre_hooks:
            if not _check_hook_execution(pre_hook, hook_candidates.pre_hooks):
                logger.error(
                    f"Transaction hash {tx_hash!r}: "
                    f"Pre-hook not executed for order {trade.order_uid!r}. "
                    f"Hook: target={pre_hook.target!r}, calldata={pre_hook.calldata!r}"
                )
                return False

    # Check post-hooks (always required, even for partially filled orders)
    for post_hook in hooks.post_hooks:
        if not _check_hook_execution(post_hook, hook_candidates.post_hooks):
            logger.error(
                f"Transaction hash {tx_hash!r}: "
                f"Post-hook not executed for order {trade.order_uid!r}. "
                f"Hook: target={post_hook.target!r}, calldata={post_hook.calldata!r}"
            )
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
          - Explicitly checked: Validated by checking offchain_trade.already_executed_amount == 0
       b. Should execute the post-hooks on every fill
          - Explicitly checked: Post-hooks are always validated regardless of fill status

    4. Execution of a hook means:
       a. There exists an internal CALL in the settlement transaction with a matching triplet:
          target, gasLimit, calldata

       b. The hook needs to be attempted, meaning the hook reverting is not violating any rules
          - NOT IMPLEMENTED: This requires transaction trace analysis to determine if the hook
            was attempted. Future implementation may require extending Hook data structure with
            an 'attempted' attribute.

       c. Intermediate calls between the call to settle and hook execution must not revert
          - NOT IMPLEMENTED: This requires transaction trace analysis to track call stack state.
            Future implementation may require extending Hook data structure with an attribute
            like 'no_upstream_revert' to indicate this validation was performed during fetching.

       d. The available gas forwarded to the hook CALL is greater or equal than specified gasLimit
          - NOT IMPLEMENTED: Gas is validated as >= required,
            If no gas cap is specified in the call, gas is set to math.inf

    Args:
        onchain_data: On-chain settlement data containing hook_candidates from transaction trace
        offchain_data: Off-chain settlement data containing expected hooks from order appData

    Returns:
        True if all required hooks were found and validated successfully, False otherwise
    """
    # If there are no trades, the rule for hooks is automatically satisfied
    if not offchain_data.trades:
        return True

    hook_candidates = onchain_data.hook_candidates

    # Check hooks for each executed trade
    for trade in offchain_data.trades:
        # Get hooks for this trade, default to empty Hooks if not present
        hooks = offchain_data.order_hooks.get(
            trade.order_uid, Hooks(pre_hooks=[], post_hooks=[])
        )

        if not _check_order_hooks(onchain_data.tx_hash, trade, hooks, hook_candidates):
            return False

    return True
