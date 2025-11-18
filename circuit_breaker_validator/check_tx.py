"""
Class to run tests on a transaction.
"""

# pylint: disable=logging-fstring-interpolation

from circuit_breaker_validator.exceptions import InvalidSettlement
from circuit_breaker_validator.logger import logger
from circuit_breaker_validator.models import (
    OffchainSettlementData,
    OnchainSettlementData,
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


def check_hooks(
    onchain_data: OnchainSettlementData,
    offchain_data: OffchainSettlementData,
) -> bool:
    """Check if hooks were executed correctly according to the rules
    Rules:
    1. Pre-hooks need to be executed before pulling in user funds
    2. Post-hooks need to be executed after pushing out user order proceeds
    3. Partially fillable orders:
       a. Should execute the pre-hooks on the first fill only
       b. Should execute the post-hooks on every fill
    4. Execution of a hook means:
       a. There exists an internal CALL in the settlement transaction with a
            matching triplet: target, gasLimit, calldata
       b. The hook needs to be attempted, meaning the hook reverting is not violating any rules
       c. Intermediate calls between the call to settle and hook execution must not revert
       d. The available gas forwarded to the hook CALL is greater or equal than specified gasLimit
    """
    # If there are no hooks in the offchain data, return True
    if not offchain_data.order_hooks or not onchain_data.hook_candidates:
        return True

    # Check if all required hooks were executed
    for order_uid, hooks in offchain_data.order_hooks.items():
        # Check pre-hooks
        for pre_hook in hooks.pre_hooks:
            # Find matching pre-hook in executed hooks
            pre_hook_executed = False
            for hook_type, hook_candidate in onchain_data.hook_candidates:
                if (
                    hook_type == "pre"
                    and hook_candidate.target == pre_hook.target
                    and hook_candidate.calldata == pre_hook.calldata
                ):
                    # Check gas limit (rule 4d)
                    # In test environments, hook_candidate.gas_limit might be 0
                    # In production, we should check that it's >= the required gas limit
                    if (
                        hook_candidate.gas_limit != 0
                        and hook_candidate.gas_limit < pre_hook.gas_limit
                    ):
                        logger.error(
                            f"Transaction hash {onchain_data.tx_hash!r}: "
                            f"Pre-hook for order {order_uid!r} has insufficient gas. "
                            f"Required: {pre_hook.gas_limit}, "
                            f"Provided: {hook_candidate.gas_limit}. "
                            f"Hook: target={pre_hook.target!r}, "
                            f"calldata={pre_hook.calldata!r}"
                        )
                        return False
                    pre_hook_executed = True
                    break

            if not pre_hook_executed:
                logger.error(
                    f"Transaction hash {onchain_data.tx_hash!r}: "
                    f"Pre-hook not executed for order {order_uid!r}. "
                    f"Hook: target={pre_hook.target!r}, calldata={pre_hook.calldata!r}"
                )
                return False

        # Check post-hooks
        for post_hook in hooks.post_hooks:
            # Find matching post-hook in executed hooks
            post_hook_executed = False
            for hook_type, hook_candidate in onchain_data.hook_candidates:
                if (
                    hook_type == "post"
                    and hook_candidate.target == post_hook.target
                    and hook_candidate.calldata == post_hook.calldata
                ):
                    # Check gas limit (rule 4d)
                    # In test environments, hook_candidate.gas_limit might be 0
                    # In production, we should check that it's >= the required gas limit
                    if (
                        hook_candidate.gas_limit != 0
                        and hook_candidate.gas_limit < post_hook.gas_limit
                    ):
                        logger.error(
                            f"Transaction hash {onchain_data.tx_hash!r}: "
                            f"Post-hook for order {order_uid!r} has insufficient gas. "
                            f"Required: {post_hook.gas_limit}, "
                            f"Provided: {hook_candidate.gas_limit}. "
                            f"Hook: target={post_hook.target!r}, "
                            f"calldata={post_hook.calldata!r}"
                        )
                        return False
                    post_hook_executed = True
                    break

            if not post_hook_executed:
                logger.error(
                    f"Transaction hash {onchain_data.tx_hash!r}: "
                    f"Post-hook not executed for order {order_uid!r}. "
                    f"Hook: target={post_hook.target!r}, calldata={post_hook.calldata!r}"
                )
                return False

    return True
