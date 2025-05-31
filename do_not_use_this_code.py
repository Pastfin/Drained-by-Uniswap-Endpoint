import time
from decimal import Decimal

import requests
from eth_account.messages import encode_typed_data
from eth_account.signers.local import LocalAccount
from web3 import Web3

from src.configure_logger import get_logger
from src.web3_base import Web3Base
from utils.proxy import get_proxy

logger = get_logger()


class SwapManager:
    def __init__(
        self,
        account: LocalAccount,
        token_in: str,
        token_out: str,
        amount: float,
        decimals_in: int,
        decimals_out: int,
        web3_base: Web3Base
    ):
        self.account = account
        self.token_in = token_in
        self.token_out = token_out
        self.amount = amount
        self.decimals_in = decimals_in
        self.decimals_out = decimals_out
        self.web3_base = web3_base
        self.amount_in_wei = str(
            int(Decimal(amount) * (Decimal(10) ** Decimal(self.decimals_in)))
        )
        self.api_key = ""

    def sign(self, permit_data):
        if not permit_data:
            return None

        message = permit_data["values"]
        message_sign = {
            "types": permit_data["types"],
            "domain": permit_data["domain"],
            "primaryType": "PermitSingle",
            "message": message
        }

        message_sign["types"]["EIP712Domain"] = [
            {"name": "name", "type": "string"},
            {"name": "chainId", "type": "uint256"},
            {"name": "verifyingContract", "type": "address"}
        ]

        message_sign["domain"]["chainId"] = str(
            message_sign["domain"]["chainId"]
        )
        message_sign["domain"]["verifyingContract"] = (
            message_sign["domain"]["verifyingContract"].lower()
        )
        message_sign["message"]["details"]["token"] = (
            message_sign["message"]["details"]["token"].lower()
        )
        message_sign["message"]["spender"] = (
            message_sign["message"]["spender"].lower()
        )

        signable_message = encode_typed_data(full_message=message_sign)
        signed = self.web3_base.web3.eth.account.sign_message(
            signable_message=signable_message,
            private_key=self.account.key
        )
        return f"0x{signed.signature.hex()}"

    def get_uniswap_quote(self):
        url = (
            "https://trading-api-labs.interface.gateway.uniswap.org/v1/quote"
        )
        headers = {
            "accept": "*/*",
            "content-type": "application/json",
            "x-api-key": self.api_key,
            "x-request-source": "uniswap-web",
            "x-universal-router-version": "2.0",
            "origin": "https://app.uniswap.org"
        }
        params = {
            "amount": self.amount_in_wei,
            "gasStrategies": [{
                "limitInflationFactor": 1.15,
                "displayLimitInflationFactor": 1,
                "priceInflationFactor": 1.5,
                "percentileThresholdFor1559Fee": 75,
                "thresholdToInflateLastBlockBaseFee": 0,
                "baseFeeMultiplier": 1.05,
                "baseFeeHistoryWindow": 100,
                "minPriorityFeeGwei": 2,
                "maxPriorityFeeGwei": 9
            }],
            "swapper": self.account.address,
            "tokenIn": self.token_in,
            "tokenInChainId": self.web3_base.web3.eth.chain_id,
            "tokenOut": self.token_out,
            "tokenOutChainId": self.web3_base.web3.eth.chain_id,
            "type": "EXACT_INPUT",
            "urgency": "normal",
            "protocols": ["V4", "V3", "V2"],
            "slippageTolerance": 0.2
        }

        response = requests.post(
            url, headers=headers, json=params, proxies=get_proxy()
        )
        if response.status_code != 200:
            raise Exception(f"Quote API error: {response.status_code}")

        return response.json()

    def get_data(self, quote, permit_data=None, signature=None):
        url = (
            "https://trading-api-labs.interface.gateway.uniswap.org/v1/swap"
        )
        headers = {
            "accept": "*/*",
            "content-type": "application/json",
            "x-api-key": self.api_key,
            "x-request-source": "uniswap-web",
            "x-universal-router-version": "2.0",
            "origin": "https://app.uniswap.org"
        }

        logger.info(quote["routeString"])

        params = {
            "quote": quote,
            "simulateTransaction": True,
            "refreshGasPrice": True,
            "gasStrategies": [{
                "limitInflationFactor": 1.15,
                "displayLimitInflationFactor": 1,
                "priceInflationFactor": 1.5,
                "percentileThresholdFor1559Fee": 75,
                "thresholdToInflateLastBlockBaseFee": 0,
                "baseFeeMultiplier": 1.05,
                "baseFeeHistoryWindow": 100,
                "minPriorityFeeGwei": 2,
                "maxPriorityFeeGwei": 9
            }],
            "urgency": "normal"
        }

        if permit_data and signature:
            params["permitData"] = permit_data
            params["signature"] = signature

        response = requests.post(
            url, headers=headers, json=params, proxies=get_proxy()
        )
        if response.status_code != 200:
            raise Exception(f"Swap API error: {response.status_code}")

        return response.json()

    def uniswap_swap(self):
        try:
            quote_data = self.get_uniswap_quote()
            quote = quote_data["quote"]
            permit_data = quote_data.get("permitData")
            sign = self.sign(permit_data) if permit_data else None
            data = self.get_data(quote, permit_data, sign)["swap"]

            tx = {
                "chainId": self.web3_base.web3.eth.chain_id,
                "from": self.account.address,
                "to": Web3.to_checksum_address(data["to"]),
                "value": int(data["value"], 16),
                "data": data["data"],
                "nonce": self.web3_base.web3.eth.get_transaction_count(
                    self.account.address
                )
            }

            receipt, tx_hash = self.web3_base.send_transaction(
                account=self.account,
                transaction=tx,
                address=Web3.to_checksum_address(data["to"]),
                value=int(data["value"], 16)
            )

            if receipt["status"] == 1:
                logger.info(
                    f"Uniswap {self.amount} swap success: 0x{tx_hash.hex()}"
                )
                return True
            else:
                raise Exception(
                    f"Swap transaction failed: 0x{tx_hash.hex()}"
                )

        except Exception as error:
            raise Exception(f"Swap error: {error}")

    def swap(self):
        for attempt in range(3):
            try:
                return self.uniswap_swap()
            except Exception as e:
                logger.error(f"Swap error: {e}")
                time.sleep(2)

        raise Exception("All swap attempts failed")
