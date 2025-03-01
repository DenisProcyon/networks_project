from typing import List

class AccountNode:
    def __init__(self, address: str):
        self.address = address
        self.children: List[AccountNode] = []