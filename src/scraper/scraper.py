import requests
import time
from typing import List

import os
from dotenv import load_dotenv

from blockchain.token import Token
from blockchain.account import AccountNode

load_dotenv()

API_KEY = os.getenv("SOLSCAN_API_KEY")
HEADERS = {
    "token": API_KEY
}

class TokenScraper:
    def __init__(self, token: Token) -> None:
        self.token = token

        self.gather_minting_data()

    def get_token_data(self) -> Token:
        return self.token

    def gather_minting_data(self) -> None:
        request_url = f'https://pro-api.solscan.io/v2.0/token/meta?address={self.token.address}'
        
        token_meta_response = requests.get(request_url, headers=HEADERS)
        if token_meta_response.status_code == 200:
            data = token_meta_response.json()["data"]

            self.token.minter = data["creator"]
            self.token.minting_time = data["created_time"]
            self.token.name = data["metadata"]["name"]
            self.token.image_link = data["metadata"]["image"]

            print(f'Got minting data for token {self.token.name}')

            return
        
        raise ConnectionError(f'Can not scrape token {self.token.address[:5]}... data. Response: {token_meta_response.status_code}')
    
class MinterTransferScraper:
    def __init__(self, token: Token, max_steps: int = 5, request_delay: float = 0.2) -> None:
        self.token = token
        self.max_steps = max_steps
        self.request_delay = request_delay

        self.root = AccountNode(token.minter)

    def fetch_transfers_for_address(self, address: str) -> List[dict]:
        base_url = "https://pro-api.solscan.io/v2.0/account/transfer"
        params = {
            "address": address,
            "activity_type[]": "ACTIVITY_SPL_TRANSFER",
            "token": self.token.address,
            "block_time[]": [
                self.token.minting_time - 60 * 60 * 24,
                self.token.minting_time + 60 * 60 * 24
            ],
            "exclude_amount_zero": "true",
            "flow": "out",
            "page": 1,
            "page_size": "100",
            "sort_by": "block_time",
            "sort_order": "desc"
        }
        
        try:
            response = requests.get(base_url, headers=HEADERS, params=params)

            time.sleep(self.request_delay)

            if response.status_code == 200:
                json_data = response.json()
                return json_data.get("data", [])
            else:
                raise ConnectionError(f'Could not connect to solscan. Status code: {response.status_code}')
        except Exception as e:
            return []

    def get_unique_transfer_accounts(self, transfers: List[dict]) -> List[str]:
        addresses = set()
        for transfer in transfers:
            to_addr = transfer.get("to_address")
            if to_addr:
                addresses.add(to_addr)

        return list(addresses)

    def process_node_children(self, node: AccountNode) -> List[AccountNode]:
        transfers = self.fetch_transfers_for_address(node.address)
        unique_addresses = self.get_unique_transfer_accounts(transfers)

        children_nodes = []
        for addr in unique_addresses:
            child_node = AccountNode(addr)
            children_nodes.append(child_node)
        
        node.children = children_nodes

        return children_nodes

    def run_scraper(self):
        current_level = [self.root]

        for depth in range(self.max_steps):
            print(f'Depth {depth + 1}')

            next_level = []

            for index, node in enumerate(current_level):
                child_list = self.process_node_children(node)
                next_level.extend(child_list)

                print(f'Processed {index + 1} out of {len(current_level)}', end="\r")

            print(f"Got {len(next_level)} nodes on depth of {depth + 1}")

            if not next_level:
                break

            current_level = next_level

    def run(self):
        self.run_scraper()