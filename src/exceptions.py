"""Exceptions for circuit breaker"""

from hexbytes import HexBytes


class NoncriticalDataFetchingError(Exception):
    """Non-critical error fetching data.
    This exception is not critical and should result in rechecking later.
    If the transaction should be checked again later, set `recheck` to be `True`. Otherwise, set it
    to `False`.
    """

    def __init__(self, message: str, /, recheck: bool) -> None:
        enhanced_message = f"{message} [recheck={recheck}]"
        super().__init__(enhanced_message)
        self.recheck: bool = recheck


class CriticalDataFetchingError(Exception):
    """Critical error fetching data.
    This exception is critical and requires immediate attention.
    """

    def __init__(self, message: str, /, solver: HexBytes) -> None:
        enhanced_message = f"{message} [solver={solver.hex()}]"
        super().__init__(enhanced_message)
        self.solver: HexBytes = solver


class MissingOnchainData(Exception):
    """This exception signals missing onchain data.
    This can happen due to nodes being out of sync.
    This exception is not critical and should result in rechecking later.
    """


class InvalidSettlement(Exception):
    """This exception signals that a check for the settlement failed.
    This only happens when all data is available and the check fails.
    It should always result in blacklisting.
    """

    def __init__(self, message: str, /, solver: HexBytes) -> None:
        enhanced_message = f"{message} [solver={solver.hex()}]"
        super().__init__(enhanced_message)
        self.solver: HexBytes = solver


class WhitelistedSolver(Exception):
    """This exception signals that a settlement comes from a whitelisted solver.
    This exception should result in skipping all checks.
    """

    def __init__(self, message: str, /, solver: HexBytes) -> None:
        enhanced_message = f"{message} [solver={solver.hex()}]"
        super().__init__(enhanced_message)
        self.solver: HexBytes = solver
