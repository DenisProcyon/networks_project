import json
from blockchain.account import AccountNode

def serialize_graph(node: AccountNode) -> dict:
    return {
        "address": node.address,
        "children": [serialize_graph(child) for child in node.children]
    }

def deserialize_graph(data: dict) -> AccountNode:
    node = AccountNode(address=data["address"])
    node.children = [deserialize_graph(i) for i in data["children"]]
    return node

def save_graph_state_to_json(root: AccountNode, frontier: list[str], filename):
    serialized = {
        "root": serialize_graph(root),
        "frontier": frontier
    }
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(serialized, f, indent=2, ensure_ascii=False)
