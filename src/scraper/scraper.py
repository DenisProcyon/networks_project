import requests
import time
from typing import List

import os
from dotenv import load_dotenv
import json

from blockchain.token import Token
from blockchain.account import AccountNode
from .utils import deserialize_graph

load_dotenv()

API_KEY = os.getenv("SOLSCAN_API_KEY")
HEADERS = {
    "token": API_KEY
}

class TokenScraper:
    """
    Scrapes token data from Solscan API. If the API call fails,
    we fallback to local step_0.json for the minter address,
    skipping the rest of the metadata (minting_time, name, image, etc.)
    """

    def __init__(self, token: Token, steps_folder: str = None) -> None:
        """
        :param token: объект Token, в котором уже есть .address
        :param steps_folder: локальная папка для step_0.json и прочих step_N.json
        """
        self.token = token
        self.steps_folder = steps_folder
        self.gather_minting_data()

    def get_token_data(self) -> Token:
        return self.token

    def gather_minting_data(self) -> None:
        request_url = f'https://pro-api.solscan.io/v2.0/token/meta?address={self.token.address}'
        
        try:
            resp = requests.get(request_url, headers=HEADERS, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()["data"]
                self.token.minter = data["creator"]
                self.token.minting_time = data["created_time"]
                self.token.name = data["metadata"]["name"]
                self.token.image_link = data["metadata"]["image"]
                
                print(f'Got minting data for token {self.token.address[:6]}... = {self.token.name}')
                return
            else:
                print(f"[WARN] Solscan response code = {resp.status_code}. Fallback to local.")
                self._fallback_local_step0()

        except Exception as e:
            print(f"[ERROR] Exception in gather_minting_data: {e}. Fallback to local.")
            self._fallback_local_step0()

    def _fallback_local_step0(self) -> None:
        if not self.steps_folder:
            print("[ERROR] steps_folder is not set, cannot fallback to local step_0.json")
            return

        step0_file = self.steps_folder / "step_0.json"
        if not step0_file.exists():
            print(f"[WARN] No step_0.json in {self.steps_folder}, cannot fallback. Minter unknown.")
            return

        try:
            with open(step0_file, encoding="utf-8") as f:
                data = json.load(f)
            root_data = data["root"]  

            root_node = deserialize_graph(root_data)
            self.token.minter = root_node.address
            self.token.minting_time = 0   
            self.token.name = f"Unknown_{self.token.address[:4]}"
            self.token.image_link = ""   
            print(f"[FALLBACK] Minter address = {self.token.minter} from step_0.json.")
        
        except Exception as e:
            print(f"[ERROR] Failed to read or parse step_0.json: {e}.")

class MinterTransferScraper:
    """
    This class scrapes transfer data of a particular token,
    starting from the minter address and exploring outgoing transfers step by step.
    it stores the result in a tree of accountnode objects and allows incremental loading.
    """
    def __init__(self, token: Token, max_steps: int = 5, request_delay: float = 0.2) -> None:
        """
        Initializes the minter transfer scraper with a given token,
        maximum depth (max_steps), and a request delay between calls.
        """
        self.token = token
        self.max_steps = max_steps
        self.request_delay = request_delay
        self.root = AccountNode(token.minter)

    def fetch_transfers_for_address(self, address: str) -> List[dict]:
        # constructs the request url and params to query the solscan api
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
                raise ConnectionError(
                    f'Could not connect to solscan. Status code: {response.status_code}'
                )
        except Exception:
            # in case of any failure, we return an empty list
            return []

    def get_unique_transfer_accounts(self, transfers: List[dict]) -> List[str]:
        # extracts unique "to" addresses from the fetched transfer records
        addresses = set()
        for transfer in transfers:
            to_addr = transfer.get("to_address")
            if to_addr:
                addresses.add(to_addr)
        return list(addresses)

    def process_node_children(self, node: AccountNode) -> List[AccountNode]:
        # fetches transfers for a single node's address, then forms child nodes
        transfers = self.fetch_transfers_for_address(node.address)
        unique_addresses = self.get_unique_transfer_accounts(transfers)

        children_nodes = []
        for addr in unique_addresses:
            child_node = AccountNode(addr)
            children_nodes.append(child_node)
        
        node.children = children_nodes
        return children_nodes

    def count_total_nodes(self, root: AccountNode) -> int:
        # performs a depth-first search to count the total number of nodes in the tree
        stack = [root]
        visited = set()
        count = 0
        while stack:
            current = stack.pop()
            if current.address not in visited:
                visited.add(current.address)
                count += 1
                stack.extend(current.children)
        return count

    def run_scraper(self, step_callback=None, steps_folder=None):
        """
        Runs the scraper step by step.
        for each depth from 1 to max_steps:
          1) checks if data/<token.address>/step_{depth}.json exists
             - if yes, loads root and frontier from that file, no api calls
             - if no, processes the frontier by calling the api for each node
               then saves the updated root+frontier to step_{depth}.json
          2) calls the step_callback if provided
        """
        if steps_folder is None:
            raise ValueError("steps_folder must be specified")

        # if step_0.json does not exist, create it with root= self.root and frontier= [root.address]
        step0_file = steps_folder / "step_0.json"
        if not step0_file.exists():
            from .utils import save_graph_state_to_json
            frontier = [self.root.address]
            save_graph_state_to_json(self.root, frontier, step0_file)
            print(f"Created {step0_file} with just the root node.")
        else:
            # if step_0.json exists, load root+frontier from it
            root_, frontier_ = self.load_graph_state_from_json(step0_file)
            self.root = root_
            print(f"Loaded existing step_0.json => root has {self.count_total_nodes(self.root)} node(s).")

        # by default, the frontier is the root node, but we actually update it each step
        current_frontier = [self.root]

        for depth in range(1, self.max_steps + 1):
            step_file = steps_folder / f"step_{depth}.json"
            
            if step_file.exists():
                # if step_{depth}.json is there, skip calls and just load root+frontier
                root_, frontier_ = self.load_graph_state_from_json(step_file)
                self.root = root_
                current_frontier = self._nodes_by_addresses(frontier_)
                print(f"[SKIP] step_{depth}.json found => skip scraping step {depth}")
            else:
                # no step file => we proceed with actual scraping
                print(f"==== Depth {depth} ====")
                new_nodes = []
                for i, node in enumerate(current_frontier):
                    child_list = self.process_node_children(node)
                    new_nodes.extend(child_list)
                    print(f"Processed {i+1} / {len(current_frontier)}", end='\r')
                print()

                current_frontier = new_nodes
                from .utils import save_graph_state_to_json
                addresses_frontier = [n.address for n in current_frontier]
                save_graph_state_to_json(self.root, addresses_frontier, step_file)
                print(f"Got {len(new_nodes)} new node(s) at depth {depth}, saved => {step_file}")

            total_count = self.count_total_nodes(self.root)
            if step_callback:
                step_callback(
                    depth=depth,
                    root=self.root,
                    total_nodes_count=total_count,
                    frontier_count=len(current_frontier),
                    token=self.token
                )

    def _nodes_by_addresses(self, addresses):
        # finds all nodes in self.root (via dfs) whose addresses are in the 'addresses' list
        stack = [self.root]
        result = []
        visited = set()
        addr_set = set(addresses)

        while stack:
            current = stack.pop()
            if current.address not in visited:
                visited.add(current.address)
                if current.address in addr_set:
                    result.append(current)
                stack.extend(current.children)
        return result

    def load_graph_state_from_json(self, path):
        # loads the stored root (as accountnode) and frontier (list of addresses) from a given json file
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        root_data = data["root"]
        frontier_data = data["frontier"]
        root_node = deserialize_graph(root_data)
        return root_node, frontier_data

    def run(self, step_callback=None, steps_folder=None):
        # runs the step-by-step scraper with optional callback and steps_folder
        self.run_scraper(step_callback=step_callback, steps_folder=steps_folder)
