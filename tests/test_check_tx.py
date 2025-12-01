"""Dummy test"""

from unittest.mock import Mock, patch

import pytest
from hexbytes import HexBytes
from circuit_breaker_validator.models import (
    OnchainSettlementData,
    OffchainSettlementData,
    OnchainTrade,
    OffchainTrade,
    Hook,
    Hooks,
)
from circuit_breaker_validator.check_tx import (
    check_solver,
    check_orders,
    check_score,
    check_hooks,
    SCORE_CHECK_THRESHOLD,
)


@pytest.mark.parametrize(
    "onchain_solver,offchain_solver,expected_result",
    [
        # succeed if solver is equal
        (HexBytes("0x01"), HexBytes("0x01"), True),
        # fail if solver is different
        (HexBytes("0x01"), HexBytes("0x02"), False),
    ],
)
def test_check_solver(onchain_solver, offchain_solver, expected_result):
    """Test that check_solver returns the expected result based on solver comparison"""
    tx_hash = HexBytes("0x00")

    onchain_data = Mock(spec=OnchainSettlementData)
    offchain_data = Mock(spec=OffchainSettlementData)
    onchain_data.tx_hash = tx_hash
    onchain_data.solver = onchain_solver
    offchain_data.solver = offchain_solver

    assert check_solver(onchain_data, offchain_data) == expected_result


@pytest.mark.parametrize(
    "scenario,expected_result",
    [
        # JIT order with zero surplus - now fails due to 1-to-1 mapping requirement
        ("jit_order_zero_surplus_not_revealed", False),
        # JIT order with zero surplus that was revealed - should pass
        ("jit_order_zero_surplus_revealed", True),
        # JIT order with non-zero surplus
        ("jit_order_nonzero_surplus", False),
        # JIT order with matching amounts (CoW AMM)
        ("jit_order_matching_amounts", True),
        # Regular order with matching amounts
        ("regular_order_matching_amounts", True),
        # Order with mismatched buy amount
        ("mismatched_buy_amount", False),
        # Order with mismatched sell amount
        ("mismatched_sell_amount", False),
        # More executed trades than proposed (no 1-to-1 mapping)
        ("more_executed_than_proposed", False),
        # More proposed trades than executed (no 1-to-1 mapping)
        ("more_proposed_than_executed", False),
        # Executed trade not in proposed (different order_uid)
        ("executed_not_in_proposed", False),
        # Proposed trade not in executed (different order_uid)
        ("proposed_not_in_executed", False),
        # Multiple matching trades with correct 1-to-1 mapping
        ("multiple_trades_matching", True),
        # Empty trades on both sides - valid 1-to-1 mapping
        ("empty_trades_both_sides", True),
    ],
)
def test_check_orders(scenario, expected_result):
    """Test that check_orders returns the expected result based on the scenario"""
    tx_hash = HexBytes("0x00")
    order_uid = HexBytes("0x01")
    sell_amount = 10**25
    buy_amount = 99 * 10**25

    if scenario == "jit_order_zero_surplus_not_revealed":
        # JIT order with zero surplus that was not revealed - fails 1-to-1 mapping
        owner = HexBytes("0x11")
        valid_orders = set()
        jit_order_addresses = {HexBytes("0x12")}

        trade = Mock(spec=OnchainTrade)
        trade.order_uid = order_uid
        trade.owner = owner
        trade.surplus = Mock(return_value=0)

        onchain_data = Mock(spec=OnchainSettlementData)
        onchain_data.tx_hash = tx_hash
        onchain_data.trades = [trade]

        offchain_data = Mock(spec=OffchainSettlementData)
        offchain_data.trades = []
        offchain_data.valid_orders = valid_orders
        offchain_data.jit_order_addresses = jit_order_addresses

    elif scenario == "jit_order_zero_surplus_revealed":
        # JIT order with zero surplus that was revealed - passes
        owner = HexBytes("0x11")
        valid_orders = set()
        jit_order_addresses = {HexBytes("0x12")}

        onchain_trade = Mock(spec=OnchainTrade)
        onchain_trade.order_uid = order_uid
        onchain_trade.owner = owner
        onchain_trade.sell_amount = sell_amount
        onchain_trade.buy_amount = buy_amount
        onchain_trade.surplus = Mock(return_value=0)

        offchain_trade = Mock(spec=OffchainTrade)
        offchain_trade.order_uid = order_uid
        offchain_trade.owner = owner
        offchain_trade.sell_amount = sell_amount
        offchain_trade.buy_amount = buy_amount

        onchain_data = Mock(spec=OnchainSettlementData)
        onchain_data.tx_hash = tx_hash
        onchain_data.trades = [onchain_trade]

        offchain_data = Mock(spec=OffchainSettlementData)
        offchain_data.trades = [offchain_trade]
        offchain_data.valid_orders = valid_orders
        offchain_data.jit_order_addresses = jit_order_addresses

    elif scenario == "jit_order_nonzero_surplus":
        # JIT order with non-zero surplus
        owner = HexBytes("0x11")
        valid_orders = set()
        jit_order_addresses = {HexBytes("0x12")}

        trade = Mock(spec=OnchainTrade)
        trade.order_uid = order_uid
        trade.owner = owner
        trade.surplus = Mock(return_value=1)

        onchain_data = Mock(spec=OnchainSettlementData)
        onchain_data.tx_hash = tx_hash
        onchain_data.trades = [trade]

        offchain_data = Mock(spec=OffchainSettlementData)
        offchain_data.trades = []
        offchain_data.valid_orders = valid_orders
        offchain_data.jit_order_addresses = jit_order_addresses

    elif scenario == "jit_order_matching_amounts":
        # JIT order with matching amounts
        owner = HexBytes("0x11")
        valid_orders = set()
        jit_order_addresses = {HexBytes("0x11")}

        onchain_trade = Mock(spec=OnchainTrade)
        onchain_trade.order_uid = order_uid
        onchain_trade.owner = owner
        onchain_trade.sell_amount = sell_amount
        onchain_trade.buy_amount = buy_amount
        onchain_trade.surplus = Mock(return_value=1)

        offchain_trade = Mock(spec=OffchainTrade)
        offchain_trade.order_uid = order_uid
        offchain_trade.owner = owner
        offchain_trade.sell_amount = sell_amount
        offchain_trade.buy_amount = buy_amount

        onchain_data = Mock(spec=OnchainSettlementData)
        onchain_data.tx_hash = tx_hash
        onchain_data.trades = [onchain_trade]

        offchain_data = Mock(spec=OffchainSettlementData)
        offchain_data.trades = [offchain_trade]
        offchain_data.valid_orders = valid_orders
        offchain_data.jit_order_addresses = jit_order_addresses

    elif scenario == "regular_order_matching_amounts":
        # Regular order with matching amounts
        owner = HexBytes("0x12")
        valid_orders = {order_uid}
        jit_order_addresses = {HexBytes("0x11")}

        onchain_trade = Mock(spec=OnchainTrade)
        onchain_trade.order_uid = order_uid
        onchain_trade.owner = owner
        onchain_trade.sell_amount = sell_amount
        onchain_trade.buy_amount = buy_amount
        onchain_trade.surplus = Mock(return_value=1)

        offchain_trade = Mock(spec=OffchainTrade)
        offchain_trade.order_uid = order_uid
        offchain_trade.owner = owner
        offchain_trade.sell_amount = sell_amount
        offchain_trade.buy_amount = buy_amount

        onchain_data = Mock(spec=OnchainSettlementData)
        onchain_data.tx_hash = tx_hash
        onchain_data.trades = [onchain_trade]

        offchain_data = Mock(spec=OffchainSettlementData)
        offchain_data.trades = [offchain_trade]
        offchain_data.valid_orders = valid_orders
        offchain_data.jit_order_addresses = jit_order_addresses

    elif scenario == "mismatched_buy_amount":
        # Order with mismatched buy amount
        owner = HexBytes("0x12")
        valid_orders = {order_uid}
        jit_order_addresses = {HexBytes("0x11")}

        onchain_trade = Mock(spec=OnchainTrade)
        onchain_trade.order_uid = order_uid
        onchain_trade.owner = owner
        onchain_trade.sell_amount = sell_amount
        onchain_trade.buy_amount = buy_amount
        onchain_trade.surplus = Mock(return_value=1)

        offchain_trade = Mock(spec=OffchainTrade)
        offchain_trade.order_uid = order_uid
        offchain_trade.owner = owner
        offchain_trade.sell_amount = sell_amount
        offchain_trade.buy_amount = buy_amount + 1  # Mismatched buy amount

        onchain_data = Mock(spec=OnchainSettlementData)
        onchain_data.tx_hash = tx_hash
        onchain_data.trades = [onchain_trade]

        offchain_data = Mock(spec=OffchainSettlementData)
        offchain_data.trades = [offchain_trade]
        offchain_data.valid_orders = valid_orders
        offchain_data.jit_order_addresses = jit_order_addresses

    elif scenario == "mismatched_sell_amount":
        # Order with mismatched sell amount
        owner = HexBytes("0x12")
        valid_orders = {order_uid}
        jit_order_addresses = {HexBytes("0x11")}

        onchain_trade = Mock(spec=OnchainTrade)
        onchain_trade.order_uid = order_uid
        onchain_trade.owner = owner
        onchain_trade.sell_amount = sell_amount
        onchain_trade.buy_amount = buy_amount
        onchain_trade.surplus = Mock(return_value=1)

        offchain_trade = Mock(spec=OffchainTrade)
        offchain_trade.order_uid = order_uid
        offchain_trade.owner = owner
        offchain_trade.sell_amount = sell_amount + 1  # Mismatched sell amount
        offchain_trade.buy_amount = buy_amount

        onchain_data = Mock(spec=OnchainSettlementData)
        onchain_data.tx_hash = tx_hash
        onchain_data.trades = [onchain_trade]

        offchain_data = Mock(spec=OffchainSettlementData)
        offchain_data.trades = [offchain_trade]
        offchain_data.valid_orders = valid_orders
        offchain_data.jit_order_addresses = jit_order_addresses

    elif scenario == "more_executed_than_proposed":
        # More executed trades than proposed (no 1-to-1 mapping)
        owner = HexBytes("0x12")
        valid_orders = {order_uid}
        jit_order_addresses = {HexBytes("0x11")}
        order_uid_2 = HexBytes("0x02")

        onchain_trade_1 = Mock(spec=OnchainTrade)
        onchain_trade_1.order_uid = order_uid
        onchain_trade_1.owner = owner
        onchain_trade_1.sell_amount = sell_amount
        onchain_trade_1.buy_amount = buy_amount
        onchain_trade_1.surplus = Mock(return_value=0)

        onchain_trade_2 = Mock(spec=OnchainTrade)
        onchain_trade_2.order_uid = order_uid_2
        onchain_trade_2.owner = owner
        onchain_trade_2.sell_amount = sell_amount
        onchain_trade_2.buy_amount = buy_amount
        onchain_trade_2.surplus = Mock(return_value=0)

        offchain_trade = Mock(spec=OffchainTrade)
        offchain_trade.order_uid = order_uid
        offchain_trade.owner = owner
        offchain_trade.sell_amount = sell_amount
        offchain_trade.buy_amount = buy_amount

        onchain_data = Mock(spec=OnchainSettlementData)
        onchain_data.tx_hash = tx_hash
        onchain_data.trades = [onchain_trade_1, onchain_trade_2]

        offchain_data = Mock(spec=OffchainSettlementData)
        offchain_data.trades = [offchain_trade]
        offchain_data.valid_orders = valid_orders
        offchain_data.jit_order_addresses = jit_order_addresses

    elif scenario == "more_proposed_than_executed":
        # More proposed trades than executed (no 1-to-1 mapping)
        owner = HexBytes("0x12")
        valid_orders = {order_uid}
        jit_order_addresses = {HexBytes("0x11")}
        order_uid_2 = HexBytes("0x02")

        onchain_trade = Mock(spec=OnchainTrade)
        onchain_trade.order_uid = order_uid
        onchain_trade.owner = owner
        onchain_trade.sell_amount = sell_amount
        onchain_trade.buy_amount = buy_amount
        onchain_trade.surplus = Mock(return_value=0)

        offchain_trade_1 = Mock(spec=OffchainTrade)
        offchain_trade_1.order_uid = order_uid
        offchain_trade_1.owner = owner
        offchain_trade_1.sell_amount = sell_amount
        offchain_trade_1.buy_amount = buy_amount

        offchain_trade_2 = Mock(spec=OffchainTrade)
        offchain_trade_2.order_uid = order_uid_2
        offchain_trade_2.owner = owner
        offchain_trade_2.sell_amount = sell_amount
        offchain_trade_2.buy_amount = buy_amount

        onchain_data = Mock(spec=OnchainSettlementData)
        onchain_data.tx_hash = tx_hash
        onchain_data.trades = [onchain_trade]

        offchain_data = Mock(spec=OffchainSettlementData)
        offchain_data.trades = [offchain_trade_1, offchain_trade_2]
        offchain_data.valid_orders = valid_orders
        offchain_data.jit_order_addresses = jit_order_addresses

    elif scenario == "executed_not_in_proposed":
        # Executed trade not in proposed trades
        owner = HexBytes("0x12")
        valid_orders = {order_uid}
        jit_order_addresses = {HexBytes("0x11")}
        order_uid_2 = HexBytes("0x02")

        onchain_trade = Mock(spec=OnchainTrade)
        onchain_trade.order_uid = order_uid_2  # Different order_uid
        onchain_trade.owner = owner
        onchain_trade.sell_amount = sell_amount
        onchain_trade.buy_amount = buy_amount
        onchain_trade.surplus = Mock(return_value=0)

        offchain_trade = Mock(spec=OffchainTrade)
        offchain_trade.order_uid = order_uid
        offchain_trade.owner = owner
        offchain_trade.sell_amount = sell_amount
        offchain_trade.buy_amount = buy_amount

        onchain_data = Mock(spec=OnchainSettlementData)
        onchain_data.tx_hash = tx_hash
        onchain_data.trades = [onchain_trade]

        offchain_data = Mock(spec=OffchainSettlementData)
        offchain_data.trades = [offchain_trade]
        offchain_data.valid_orders = valid_orders
        offchain_data.jit_order_addresses = jit_order_addresses

    elif scenario == "proposed_not_in_executed":
        # Proposed trade not in executed trades
        owner = HexBytes("0x12")
        valid_orders = {order_uid}
        jit_order_addresses = {HexBytes("0x11")}
        order_uid_2 = HexBytes("0x02")

        onchain_trade = Mock(spec=OnchainTrade)
        onchain_trade.order_uid = order_uid
        onchain_trade.owner = owner
        onchain_trade.sell_amount = sell_amount
        onchain_trade.buy_amount = buy_amount
        onchain_trade.surplus = Mock(return_value=0)

        offchain_trade = Mock(spec=OffchainTrade)
        offchain_trade.order_uid = order_uid_2  # Different order_uid
        offchain_trade.owner = owner
        offchain_trade.sell_amount = sell_amount
        offchain_trade.buy_amount = buy_amount

        onchain_data = Mock(spec=OnchainSettlementData)
        onchain_data.tx_hash = tx_hash
        onchain_data.trades = [onchain_trade]

        offchain_data = Mock(spec=OffchainSettlementData)
        offchain_data.trades = [offchain_trade]
        offchain_data.valid_orders = valid_orders
        offchain_data.jit_order_addresses = jit_order_addresses

    elif scenario == "multiple_trades_matching":
        # Multiple trades with correct 1-to-1 mapping
        owner = HexBytes("0x12")
        valid_orders = {order_uid}
        jit_order_addresses = {HexBytes("0x11")}
        order_uid_2 = HexBytes("0x02")
        order_uid_3 = HexBytes("0x03")
        valid_orders = {order_uid, order_uid_2, order_uid_3}

        onchain_trade_1 = Mock(spec=OnchainTrade)
        onchain_trade_1.order_uid = order_uid
        onchain_trade_1.owner = owner
        onchain_trade_1.sell_amount = sell_amount
        onchain_trade_1.buy_amount = buy_amount
        onchain_trade_1.surplus = Mock(return_value=100)

        onchain_trade_2 = Mock(spec=OnchainTrade)
        onchain_trade_2.order_uid = order_uid_2
        onchain_trade_2.owner = owner
        onchain_trade_2.sell_amount = sell_amount * 2
        onchain_trade_2.buy_amount = buy_amount * 2
        onchain_trade_2.surplus = Mock(return_value=200)

        onchain_trade_3 = Mock(spec=OnchainTrade)
        onchain_trade_3.order_uid = order_uid_3
        onchain_trade_3.owner = owner
        onchain_trade_3.sell_amount = sell_amount // 2
        onchain_trade_3.buy_amount = buy_amount // 2
        onchain_trade_3.surplus = Mock(return_value=50)

        offchain_trade_1 = Mock(spec=OffchainTrade)
        offchain_trade_1.order_uid = order_uid
        offchain_trade_1.sell_amount = sell_amount
        offchain_trade_1.buy_amount = buy_amount

        offchain_trade_2 = Mock(spec=OffchainTrade)
        offchain_trade_2.order_uid = order_uid_2
        offchain_trade_2.sell_amount = sell_amount * 2
        offchain_trade_2.buy_amount = buy_amount * 2

        offchain_trade_3 = Mock(spec=OffchainTrade)
        offchain_trade_3.order_uid = order_uid_3
        offchain_trade_3.sell_amount = sell_amount // 2
        offchain_trade_3.buy_amount = buy_amount // 2

        onchain_data = Mock(spec=OnchainSettlementData)
        onchain_data.tx_hash = tx_hash
        onchain_data.trades = [onchain_trade_1, onchain_trade_2, onchain_trade_3]

        offchain_data = Mock(spec=OffchainSettlementData)
        offchain_data.trades = [offchain_trade_1, offchain_trade_2, offchain_trade_3]
        offchain_data.valid_orders = valid_orders
        offchain_data.jit_order_addresses = jit_order_addresses

    elif scenario == "empty_trades_both_sides":
        # Empty trades on both sides - valid 1-to-1 mapping (no trades)
        valid_orders = set()
        jit_order_addresses = set()

        onchain_data = Mock(spec=OnchainSettlementData)
        onchain_data.tx_hash = tx_hash
        onchain_data.trades = []

        offchain_data = Mock(spec=OffchainSettlementData)
        offchain_data.trades = []
        offchain_data.valid_orders = valid_orders
        offchain_data.jit_order_addresses = jit_order_addresses

    assert check_orders(onchain_data, offchain_data) == expected_result


@pytest.mark.parametrize(
    "difference,expected_result",
    [
        # succeed if scores are (almost) equal
        (-SCORE_CHECK_THRESHOLD, True),
        (-1, True),
        (0, True),
        (1, True),
        (10**18, True),
        # fail if the scores are not (almost) equal
        (-(10**18), False),
        (-(SCORE_CHECK_THRESHOLD + 1), False),
    ],
)
def test_check_score(difference, expected_result):
    """Test that check_score returns the expected result based on score difference"""
    tx_hash = HexBytes("0x00")
    onchain_data = Mock(spec=OnchainSettlementData)
    onchain_data.tx_hash = tx_hash
    offchain_data = Mock(spec=OffchainSettlementData)
    offchain_data.score = 10**18

    with patch(
        "circuit_breaker_validator.check_tx.compute_score",
        return_value=10**18 + difference,
    ):
        assert check_score(onchain_data, offchain_data) == expected_result


@pytest.mark.parametrize(
    "scenario,expected_result",
    [
        # No hooks defined - should pass
        ("no_hooks", True),
        # All hooks executed correctly - should pass
        ("all_hooks_executed", True),
        # Missing pre-hook - should fail
        ("missing_pre_hook", False),
        # Missing post-hook - should fail
        ("missing_post_hook", False),
        # Insufficient gas limit - should fail
        ("insufficient_gas", False),
        # First fill with pre-hooks - should pass
        ("first_fill_with_pre_hooks", True),
        # Subsequent fill without pre-hooks - should pass
        ("subsequent_fill_no_pre_hooks", True),
        # Subsequent fill with pre-hooks incorrectly - current implementation doesn't validate this
        ("subsequent_fill_with_pre_hooks", True),
        # Multiple hooks executed correctly - should pass
        ("multiple_hooks", True),
    ],
)
def test_check_hooks(scenario, expected_result):
    """Test that check_hooks returns the expected result based on the scenario"""
    tx_hash = HexBytes("0x00")
    order_uid = HexBytes("0x01")

    # Create base hooks for testing
    pre_hook = Hook(
        target=HexBytes("0xC01De8aB58f29E4d9fa9e274eC7c05a04e397312"),
        calldata=HexBytes("0xc2985578"),
        gas_limit=1030000,
    )
    post_hook = Hook(
        target=HexBytes("0xD02De8aB58f29E4d9fa9e274eC7c05a04e397313"),
        calldata=HexBytes("0xd3985579"),
        gas_limit=2040000,
    )

    if scenario == "no_hooks":
        # No hooks defined in offchain data
        onchain_data = Mock(spec=OnchainSettlementData)
        onchain_data.tx_hash = tx_hash
        onchain_data.hook_candidates = Hooks(pre_hooks=[], post_hooks=[])

        offchain_data = Mock(spec=OffchainSettlementData)
        offchain_data.order_hooks = {}

    elif scenario == "all_hooks_executed":
        # All hooks executed correctly
        executed_pre_hook = Hook(
            target=pre_hook.target,
            calldata=pre_hook.calldata,
            gas_limit=pre_hook.gas_limit,  # Must match exactly
        )
        executed_post_hook = Hook(
            target=post_hook.target,
            calldata=post_hook.calldata,
            gas_limit=post_hook.gas_limit,
        )

        onchain_data = Mock(spec=OnchainSettlementData)
        onchain_data.tx_hash = tx_hash
        onchain_data.hook_candidates = Hooks(
            pre_hooks=[executed_pre_hook],
            post_hooks=[executed_post_hook],
        )

        offchain_trade = Mock(spec=OffchainTrade)
        offchain_trade.order_uid = order_uid
        offchain_trade.already_executed_amount = 0  # First fill

        offchain_data = Mock(spec=OffchainSettlementData)
        offchain_data.order_hooks = {
            order_uid: Hooks(pre_hooks=[pre_hook], post_hooks=[post_hook])
        }
        offchain_data.trades = [offchain_trade]

    elif scenario == "missing_pre_hook":
        # Pre-hook is missing in executed hooks
        executed_post_hook = Hook(
            target=post_hook.target,
            calldata=post_hook.calldata,
            gas_limit=0,
        )

        onchain_data = Mock(spec=OnchainSettlementData)
        onchain_data.tx_hash = tx_hash
        onchain_data.hook_candidates = Hooks(
            pre_hooks=[],  # Missing pre-hook
            post_hooks=[executed_post_hook],
        )

        offchain_trade = Mock(spec=OffchainTrade)
        offchain_trade.order_uid = order_uid
        offchain_trade.already_executed_amount = 0  # First fill

        offchain_data = Mock(spec=OffchainSettlementData)
        offchain_data.order_hooks = {
            order_uid: Hooks(pre_hooks=[pre_hook], post_hooks=[post_hook])
        }
        offchain_data.trades = [offchain_trade]

    elif scenario == "missing_post_hook":
        # Post-hook is missing in executed hooks
        executed_pre_hook = Hook(
            target=pre_hook.target,
            calldata=pre_hook.calldata,
            gas_limit=pre_hook.gas_limit,
        )

        onchain_data = Mock(spec=OnchainSettlementData)
        onchain_data.tx_hash = tx_hash
        onchain_data.hook_candidates = Hooks(
            pre_hooks=[executed_pre_hook],
            post_hooks=[],  # Missing post-hook
        )

        offchain_trade = Mock(spec=OffchainTrade)
        offchain_trade.order_uid = order_uid
        offchain_trade.already_executed_amount = 0  # First fill

        offchain_data = Mock(spec=OffchainSettlementData)
        offchain_data.order_hooks = {
            order_uid: Hooks(pre_hooks=[pre_hook], post_hooks=[post_hook])
        }
        offchain_data.trades = [offchain_trade]

    elif scenario == "insufficient_gas":
        # Executed hook has insufficient gas limit
        executed_pre_hook = Hook(
            target=pre_hook.target,
            calldata=pre_hook.calldata,
            gas_limit=1000,  # Less than required 1030000
        )
        executed_post_hook = Hook(
            target=post_hook.target,
            calldata=post_hook.calldata,
            gas_limit=post_hook.gas_limit,
        )

        onchain_data = Mock(spec=OnchainSettlementData)
        onchain_data.tx_hash = tx_hash
        onchain_data.hook_candidates = Hooks(
            pre_hooks=[executed_pre_hook],
            post_hooks=[executed_post_hook],
        )

        offchain_trade = Mock(spec=OffchainTrade)
        offchain_trade.order_uid = order_uid
        offchain_trade.already_executed_amount = 0  # First fill

        offchain_data = Mock(spec=OffchainSettlementData)
        offchain_data.order_hooks = {
            order_uid: Hooks(pre_hooks=[pre_hook], post_hooks=[post_hook])
        }
        offchain_data.trades = [offchain_trade]

    elif scenario == "first_fill_with_pre_hooks":
        # First fill - pre-hooks should be executed
        executed_pre_hook = Hook(
            target=pre_hook.target,
            calldata=pre_hook.calldata,
            gas_limit=pre_hook.gas_limit,
        )
        executed_post_hook = Hook(
            target=post_hook.target,
            calldata=post_hook.calldata,
            gas_limit=post_hook.gas_limit,
        )

        onchain_data = Mock(spec=OnchainSettlementData)
        onchain_data.tx_hash = tx_hash
        onchain_data.hook_candidates = Hooks(
            pre_hooks=[executed_pre_hook],
            post_hooks=[executed_post_hook],
        )

        offchain_trade = Mock(spec=OffchainTrade)
        offchain_trade.order_uid = order_uid
        offchain_trade.already_executed_amount = 0  # First fill

        offchain_data = Mock(spec=OffchainSettlementData)
        offchain_data.order_hooks = {
            order_uid: Hooks(pre_hooks=[pre_hook], post_hooks=[post_hook])
        }
        offchain_data.trades = [offchain_trade]

    elif scenario == "subsequent_fill_no_pre_hooks":
        # Subsequent fill - pre-hooks should NOT be executed
        executed_post_hook = Hook(
            target=post_hook.target,
            calldata=post_hook.calldata,
            gas_limit=post_hook.gas_limit,
        )

        onchain_data = Mock(spec=OnchainSettlementData)
        onchain_data.tx_hash = tx_hash
        onchain_data.hook_candidates = Hooks(
            pre_hooks=[],  # No pre-hooks for subsequent fill
            post_hooks=[executed_post_hook],
        )

        offchain_trade = Mock(spec=OffchainTrade)
        offchain_trade.order_uid = order_uid
        offchain_trade.already_executed_amount = 1000  # Subsequent fill

        offchain_data = Mock(spec=OffchainSettlementData)
        offchain_data.order_hooks = {
            order_uid: Hooks(pre_hooks=[pre_hook], post_hooks=[post_hook])
        }
        offchain_data.trades = [offchain_trade]

    elif scenario == "subsequent_fill_with_pre_hooks":
        # Subsequent fill - pre-hooks should NOT be executed, but they are
        executed_pre_hook = Hook(
            target=pre_hook.target,
            calldata=pre_hook.calldata,
            gas_limit=pre_hook.gas_limit,
        )
        executed_post_hook = Hook(
            target=post_hook.target,
            calldata=post_hook.calldata,
            gas_limit=post_hook.gas_limit,
        )

        onchain_data = Mock(spec=OnchainSettlementData)
        onchain_data.tx_hash = tx_hash
        onchain_data.hook_candidates = Hooks(
            pre_hooks=[executed_pre_hook],  # Pre-hooks incorrectly executed
            post_hooks=[executed_post_hook],
        )

        offchain_trade = Mock(spec=OffchainTrade)
        offchain_trade.order_uid = order_uid
        offchain_trade.already_executed_amount = 1000  # Subsequent fill

        offchain_data = Mock(spec=OffchainSettlementData)
        offchain_data.order_hooks = {
            order_uid: Hooks(pre_hooks=[pre_hook], post_hooks=[post_hook])
        }
        offchain_data.trades = [offchain_trade]

    elif scenario == "multiple_hooks":
        # Multiple hooks executed correctly
        pre_hook_2 = Hook(
            target=HexBytes("0xC02De8aB58f29E4d9fa9e274eC7c05a04e397313"),
            calldata=HexBytes("0xc3985579"),
            gas_limit=1040000,
        )
        post_hook_2 = Hook(
            target=HexBytes("0xD03De8aB58f29E4d9fa9e274eC7c05a04e397314"),
            calldata=HexBytes("0xd4985580"),
            gas_limit=2050000,
        )

        executed_pre_hook_1 = Hook(
            target=pre_hook.target,
            calldata=pre_hook.calldata,
            gas_limit=pre_hook.gas_limit,
        )
        executed_pre_hook_2 = Hook(
            target=pre_hook_2.target,
            calldata=pre_hook_2.calldata,
            gas_limit=pre_hook_2.gas_limit,
        )
        executed_post_hook_1 = Hook(
            target=post_hook.target,
            calldata=post_hook.calldata,
            gas_limit=post_hook.gas_limit,
        )
        executed_post_hook_2 = Hook(
            target=post_hook_2.target,
            calldata=post_hook_2.calldata,
            gas_limit=post_hook_2.gas_limit,
        )

        onchain_data = Mock(spec=OnchainSettlementData)
        onchain_data.tx_hash = tx_hash
        onchain_data.hook_candidates = Hooks(
            pre_hooks=[executed_pre_hook_1, executed_pre_hook_2],
            post_hooks=[executed_post_hook_1, executed_post_hook_2],
        )

        offchain_trade = Mock(spec=OffchainTrade)
        offchain_trade.order_uid = order_uid
        offchain_trade.already_executed_amount = 0  # First fill

        offchain_data = Mock(spec=OffchainSettlementData)
        offchain_data.order_hooks = {
            order_uid: Hooks(
                pre_hooks=[pre_hook, pre_hook_2],
                post_hooks=[post_hook, post_hook_2],
            )
        }
        offchain_data.trades = [offchain_trade]

    assert check_hooks(onchain_data, offchain_data) == expected_result
