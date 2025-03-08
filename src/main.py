from scraper.scraper import TokenScraper, MinterTransferScraper
from blockchain.token import Token
from blockchain.account import AccountNode

import networkx as nx
import matplotlib.pyplot as plt
import json
from pathlib import Path
import os

def build_graph_from_node(node: AccountNode, graph: nx.DiGraph):
    for child in node.children:
        graph.add_edge(node.address, child.address)
        build_graph_from_node(child, graph)

def plot_graph_from_root(root: AccountNode, title: str = "Token Transfer Graph"):
    """ Рисуем текущую структуру дерева/графа. """
    G = nx.DiGraph()
    build_graph_from_node(root, G)

    node_list = list(G.nodes())
    pos = nx.kamada_kawai_layout(G)

    node_colors = ["skyblue"] * len(node_list)
    if root.address in node_list:
        idx = node_list.index(root.address)
        node_colors[idx] = "red"

    # Для лейблов выделяем только root + top-N самых "связных" узлов
    labels = {root.address: "ROOT"}
    top_n = 10
    degrees = sorted(G.degree(), key=lambda x: x[1], reverse=True)
    top_nodes = [addr for (addr, deg) in degrees[:top_n]]
    for node in top_nodes:
        if node != root.address:
            labels[node] = node[:6] + "..."

    plt.figure(figsize=(10, 6))
    nx.draw_networkx_nodes(G, pos, nodelist=node_list, node_size=100, node_color=node_colors, alpha=0.8)
    nx.draw_networkx_labels(G, pos, labels=labels, font_size=8)
    nx.draw_networkx_edges(G, pos, arrowstyle="->", arrowsize=7, width=0.5, alpha=0.6, edge_color="gray")
    plt.title(title)
    plt.axis("off")
    plt.show()


# -------------------------
#   ФУНКЦИЯ-коллбэк
#   (Вызывается на каждом шаге)
# -------------------------
def step_callback(depth: int, root: AccountNode, total_nodes_count: int, frontier_count: int, token: Token):
    """
    depth            - текущий шаг (1..max_steps)
    root             - корневой узел (уже обновлённый)
    total_nodes_count- общее кол-во узлов в графе после этого шага
    frontier_count   - кол-во новых адресов на этом шаге
    token            - объект токена (token.address и пр.)
    """

    print(f"[CALLBACK] Step={depth}, total_nodes={total_nodes_count}, frontier={frontier_count}")

    # 1) Сначала построим сам граф (узлы/рёбра)
    G = nx.DiGraph()
    build_graph_from_node(root, G)
    edge_count = G.number_of_edges()

    # 2) Храним «историю» в полях функции, чтобы при каждом вызове 
    #    мы могли рисовать накопленную динамику
    if not hasattr(step_callback, "history"):
        step_callback.history = {
            "steps": [],
            "nodes": [],
            "edges": []
        }

    step_callback.history["steps"].append(depth)
    step_callback.history["nodes"].append(total_nodes_count)
    step_callback.history["edges"].append(edge_count)

    # 3) Рисуем саму сеть
    plot_graph_from_root(
        root,
        title=f"Graph after step={depth}, total_nodes={total_nodes_count}, edges={edge_count}"
    )

    # 4) Теперь строим общий линейный граф (Nodes vs Edges)
    steps = step_callback.history["steps"]
    node_counts = step_callback.history["nodes"]
    edge_counts = step_callback.history["edges"]

    plt.figure(figsize=(8, 5))
    # Пользователь просил «красиво, с приятными цветами, гридом и т.п.»
    # Будем использовать базовые цвета, легенду, метки, сетку
    plt.plot(steps, node_counts, marker='o', label='Nodes')
    plt.plot(steps, edge_counts, marker='o', label='Edges')
    plt.title("Nodes & Edges Over Steps")
    plt.xlabel("Step")
    plt.ylabel("Count")
    plt.grid(True)
    plt.legend()
    plt.show()

def get_final_nx_graph(root):
    """
    Создаём networkx.DiGraph из корневого узла root.
    """
    G = nx.DiGraph()
    build_graph_from_node(root, G)
    return G

def analyze_final_graph(root):
    """
    Получает полностью построенный root (с детьми) и 
    рассчитывает метрики для финального графа.
    """
    # 1) Формируем DiGraph из вашего дерева
    G = get_final_nx_graph(root)

    print("=== Analyzing Final Graph ===")
    print(f"Total nodes: {G.number_of_nodes()}, edges: {G.number_of_edges()}")

    # --------------------------
    # 2) Degree Distribution
    # --------------------------
    in_degs  = [d for _, d in G.in_degree()]
    out_degs = [d for _, d in G.out_degree()]
    # (а) распечатаем средние
    avg_in  = sum(in_degs)  / len(in_degs) if in_degs else 0
    avg_out = sum(out_degs) / len(out_degs) if out_degs else 0
    print(f"Average in-degree:  {avg_in:.2f}")
    print(f"Average out-degree: {avg_out:.2f}")

    # (б) хотим сделать логарифмический график распределения in-degree
    plt.figure()
    plt.hist(in_degs, bins=100, log=True)  # log-scale по оси Y
    plt.title("In-degree distribution (log scale on Y)")
    plt.xlabel("In-degree")
    plt.ylabel("Count (log scale)")
    plt.grid(True)
    plt.show()

    # То же самое для out-degree
    plt.figure()
    plt.hist(out_degs, bins=100, log=True)
    plt.title("Out-degree distribution (log scale on Y)")
    plt.xlabel("Out-degree")
    plt.ylabel("Count (log scale)")
    plt.grid(True)
    plt.show()

    # --------------------------
    # 3) Clustering
    # --------------------------
    # Для ориентированного графа NetworkX не считает clustering напрямую.
    # Часто либо берем G.to_undirected(), либо считаем только "weakly connected".
    # Ниже — простой пример для undirected:
    undirected_G = G.to_undirected()
    avg_clustering = nx.average_clustering(undirected_G)
    print(f"Average clustering (undirected): {avg_clustering:.4f}")

    # --------------------------
    # 4) Average Shortest Path
    # --------------------------
    # Если граф большой и неодносвязный, прямое вычисление может быть тяжёлым.
    # (nx.average_shortest_path_length требует сильной или слабой связности).
    # Ниже пример для крупнейшего слабосвязного компонента:
    largest_cc = max(nx.weakly_connected_components(G), key=len)
    subG = G.subgraph(largest_cc).copy()
    # Далее переводим в undirected, чтобы обойти DirectedDisconnectedError,
    # но это уже зависит от вашей логики:
    subG_und = subG.to_undirected()
    if nx.is_connected(subG_und):
        spl = nx.average_shortest_path_length(subG_und)
        print(f"Avg shortest path length (largest WCC, undirected): {spl:.4f}")
    else:
        print("Largest WCC is not fully connected even in undirected sense.")

    # --------------------------
    # 5) Connected Components
    # --------------------------
    # (a) Strongly connected
    scc = list(nx.strongly_connected_components(G))
    scc_sizes = [len(c) for c in scc]
    print(f"Number of strongly connected components: {len(scc_sizes)}")
    print(f"Largest SCC size: {max(scc_sizes) if scc_sizes else 0}")

    # (b) Weakly connected
    wcc = list(nx.weakly_connected_components(G))
    wcc_sizes = [len(c) for c in wcc]
    print(f"Number of weakly connected components: {len(wcc_sizes)}")
    print(f"Largest WCC size: {max(wcc_sizes) if wcc_sizes else 0}")

    # --------------------------
    # 6) Centralities
    # --------------------------
    # Для больших графов betweenness и closeness могут быть затратны, 
    # но для иллюстрации:
    print("Computing betweenness_centrality (might be slow for large graphs).")
    bc = nx.betweenness_centrality(G, k=None, normalized=True)  
    # k=None => точное вычисление, можно k=100 для approx
    print("Computing closeness_centrality.")
    cc = nx.closeness_centrality(G)

    # Можно вывести top-5 узлов по этим метрикам:
    top_betw = sorted(bc.items(), key=lambda x: x[1], reverse=True)[:5]
    top_close = sorted(cc.items(), key=lambda x: x[1], reverse=True)[:5]
    print("Top-5 by betweenness_centrality:", top_betw)
    print("Top-5 by closeness_centrality:  ", top_close)

    # Можно также построить гистограмму betweenness
    bc_vals = list(bc.values())
    plt.figure()
    plt.hist(bc_vals, bins=50, log=True)
    plt.title("Betweenness centrality distribution")
    plt.xlabel("Betweenness centrality")
    plt.ylabel("Count (log scale)")
    plt.grid(True)
    plt.show()

    # --------------------------
    # 7) Assortativity
    # --------------------------
    # В networkx есть "nx.degree_assortativity_coefficient" 
    # но для ориентированного нужно аккуратно:
    # Можно считать out->in:
    r_inout = nx.degree_pearson_correlation_coefficient(G, x='out', y='in')
    print(f"Degree Pearson correlation (out->in) = {r_inout:.4f}")
    # < 0 => disassortative, > 0 => assortative

    # --------------------------
    # 8) Rich-club Coefficient
    # --------------------------
    # В networkx "nx.rich_club_coefficient" работает для undirected, 
    # поэтому:
    rc = nx.rich_club_coefficient(G.to_undirected(), normalized=False)
    # Возвращает словарь: {k: phi(k)}. Обычно смотрят, растёт ли phi(k) с k,
    # и сравнивают с рандомной моделью.
    # Выведем часть результатов:
    sorted_k = sorted(rc.keys())
    print("Rich-club coefficient (un-normalized):")
    for k in sorted_k[:10]:
        print(f" k={k}: phi={rc[k]}")


if __name__ == "__main__":
    TOKEN_ADDRESS = "FUAfBo2jgks6gB4Z4LfZkqSZgzNucisEHqnNebaRxM1P"
    MAX_STEPS = 6

    # Папка, где храним step_*.json
    steps_folder = Path("data") / TOKEN_ADDRESS
    steps_folder.mkdir(parents=True, exist_ok=True)

    # Инициализация токена
    token_obj = TokenScraper(Token(address=TOKEN_ADDRESS)).get_token_data()
    scraper = MinterTransferScraper(token=token_obj, max_steps=MAX_STEPS)

    # Запускаем пошаговый скрейпер, указывая steps_folder и коллбэк
    scraper.run(
        step_callback=step_callback,
        steps_folder=steps_folder
    )
