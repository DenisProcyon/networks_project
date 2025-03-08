from scraper.scraper import TokenScraper, MinterTransferScraper
from blockchain.token import Token
from blockchain.account import AccountNode

import networkx as nx
import matplotlib.pyplot as plt
import matplotlib.cm as cm

import json
from pathlib import Path

def build_graph_from_node(node: AccountNode, graph: nx.DiGraph):
    for child in node.children:
        graph.add_edge(node.address, child.address)
        build_graph_from_node(child, graph)


def plot_graph_from_root(root: AccountNode):
    G = nx.DiGraph()
    build_graph_from_node(root, G)

    node_list = list(G.nodes())
    
    pos = nx.kamada_kawai_layout(G)  

    node_colors = ["skyblue"] * len(node_list)

    if root.address in node_list:
        idx = node_list.index(root.address)
        node_colors[idx] = "red"

    labels = {}
    labels[root.address] = "ROOT"

    top_n = 10
    degrees = sorted(G.degree(), key=lambda x: x[1], reverse=True)
    top_nodes = [addr for (addr, deg) in degrees[:top_n]]
    for node in top_nodes:
        if node != root.address:
            labels[node] = node[:6] + "..."

    plt.figure(figsize=(15, 10)) 

    nx.draw_networkx_nodes(
        G,
        pos,
        nodelist=node_list,
        node_size=100,     
        node_color=node_colors,
        alpha=0.8
    )
    
    nx.draw_networkx_labels(
        G,
        pos,
        labels=labels,
        font_size=8
    )

    nx.draw_networkx_edges(
        G,
        pos,
        arrowstyle="->",
        arrowsize=7,
        width=0.5,   
        alpha=0.6,
        edge_color="gray"
    )
    
    plt.title("Graph of token transfers (root - red)")
    plt.axis("off")
    plt.show()

def serialize_graph(node: AccountNode) -> dict:
    return {
        "address": node.address,
        "children": [serialize_graph(child) for child in node.children]
    }

def save_graph_to_json(root: AccountNode, filename: str):
    serialized = serialize_graph(root)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(serialized, f, indent=2, ensure_ascii=False)

def deserialize_graph(data: dict[str]) -> dict[AccountNode]:
    node = AccountNode(address=data["address"])
    node.children = [deserialize_graph(i) for i in data["children"]]

    return node
    
def get_root_from_local(filename: str) -> dict[AccountNode]:
    path = Path(__file__).parent / filename
    if path.exists():
        print(f'{filename} found locally')
        
        with open(path) as file:
            data = json.load(file)

        graph = deserialize_graph(data=data)

        return graph
    
    print(f'No {filename} file found')

if __name__ == "__main__":
    TOKEN = "5d2TbDMFmnH3BzwGtGQ2nAmq2ysLu3YCCrT5ftf6moon"
    MAX_STEPS = 4
    
    file = f'{TOKEN}_{MAX_STEPS}.json'

    root = get_root_from_local(file)
    if root is None:
        token = TokenScraper(
            token=Token(address=TOKEN)
        ).get_token_data()

        scraper = MinterTransferScraper(token=token, max_steps=MAX_STEPS)
        scraper.run()

        root = scraper.root

    serialized_graph = save_graph_to_json(root, file)

    plot_graph_from_root(root)
