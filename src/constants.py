"""
All Constants that are used throughout the project
"""

from hexbytes import HexBytes
from eth_typing import Address

AWS_PROD_BASE_URL = "https://solver-instances.s3.eu-central-1.amazonaws.com/prod/"
AWS_STAGING_BASE_URL = "https://solver-instances.s3.eu-central-1.amazonaws.com/staging/"
ORDERBOOK_PROD_BASE_URL = "https://api.cow.fi/"
ORDERBOOK_STAGING_BASE_URL = "https://barn.api.cow.fi/"

SETTLEMENT_CONTRACT_ADDRESS = HexBytes("0x9008D19f58AAbD9eD0D60971565AA8510560ab41")
SETTLE_CALL_SIGNATURE = HexBytes("0x13d79a0b")

# This is a whitelisted solver address
TEAM_MULTISIG = HexBytes("0x423cec87f19f0778f549846e0801ee267a917935")

REQUEST_TIMEOUT = 5
RPC_RETRIES_BACKOFF_FACTOR = (
    0.5  # with the default of 5 retries, this results in a final cumulative delay of around
    # REQUEST_TIMEOUT +
    # sum(RPC_RETRIES_BACKOFF_FACTOR * 2**i + REQUEST_TIMEOUT for i in range(5))
    # i.e. around 45 seconds
)

CHAIN_ID_TO_SLEEP_TIME = {
    1: 1,
    100: 1,
    8453: 1,
    42161: 1,
    43114: 1,
    137: 1,
    11155111: 10,
    232: 1,
}

CHAIN_ID_TO_API_NAME = {
    1: "mainnet",
    100: "xdai",
    8453: "base",
    42161: "arbitrum_one",
    43114: "avalanche",
    137: "polygon",
    11155111: "sepolia",
    232: "lens",
}

CHAIN_ID_TO_AWS_BUCKET_NAME = {
    1: "mainnet",
    100: "xdai",
    8453: "base",
    42161: "arbitrum-one",
    43114: "avalanche",
    137: "polygon",
    11155111: "sepolia",
    232: "lens",
}

CHAIN_ID_TO_ZODIAC_MODULE_ADDRESS = {
    1: Address(HexBytes("0xadc87ecf8ff4009982893f17704394a15bbc25c4")),
    100: Address(HexBytes("0x6C24186013B921fFB800CB37a5CCe232a8B76112")),
    42161: Address(HexBytes("0x05cb678a7a38649c52684273f8b724d4bd3c331d")),
    8453: Address(HexBytes("0x5b03de084dc3744aa871f8fc81493e4fc373c1be")),
}

FINALIZE_THRESHOLD = 64

# This is the maximum number of retries until a hash is skipped
RECHECK_THRESHOLD = 128

NATIVE_TOKEN_PRICE = 10**18

GPV2_AUTHENTICATOR = Address(HexBytes("0x9E7Ae8Bdba9AA346739792d219a808884996Db67"))
GPV2_AUTHENTICATOR_PROXY = Address(
    HexBytes("0x2c4c28DDBdAc9C5E7055b4C863b72eA0149D8aFE")
)

FLASH_LOAN_ROUTER = HexBytes("0x9da8B48441583a2b93e2eF8213aAD0EC0b392C69")

EXTRADATA_PATCH_CHAINS = {
    43114,
    137,
}  # These chains have longer extraData fields and require patching in 'data_fetching/web3_api.py'
