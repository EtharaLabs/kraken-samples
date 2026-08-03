"""Workload for networkx#7971: Speed up connected_components and weakly_connected_components.

The optimization passes `n - len(seen)` instead of `n` to _plain_bfs, allowing
BFS to terminate early once it finds all remaining unseen nodes. Biggest speedup
on disconnected graphs with many large components.
"""
import multiprocessing
import sys
import timeit


def _child_target():
    import networkx as nx

    # Worst case: disconnected graph with one large component + one node
    # (triggers the optimization: after finding large component, BFS for single node is trivial)
    G_disconnected = nx.complete_graph(500)
    # Add 500 isolated nodes
    G_disconnected.add_nodes_from(range(500, 1000))

    # Multiple medium components
    G_multi = nx.Graph()
    for i in range(20):
        component = nx.gnp_random_graph(100, 0.1, seed=i)
        mapping = {n: n + i * 100 for n in component.nodes()}
        G_multi = nx.compose(G_multi, nx.relabel_nodes(component, mapping))

    # Directed graph for weakly_connected_components
    G_directed = nx.DiGraph()
    for i in range(10):
        component = nx.gnp_random_graph(200, 0.05, seed=i, directed=True)
        mapping = {n: n + i * 200 for n in component.nodes()}
        G_directed = nx.compose(G_directed, nx.relabel_nodes(component, mapping))

    def workload():
        # connected_components on disconnected graph
        list(nx.connected_components(G_disconnected))
        list(nx.connected_components(G_disconnected))
        list(nx.connected_components(G_disconnected))
        # connected_components on multi-component graph
        list(nx.connected_components(G_multi))
        list(nx.connected_components(G_multi))
        # weakly_connected_components
        list(nx.weakly_connected_components(G_directed))
        list(nx.weakly_connected_components(G_directed))

    # Warm up
    workload()

    times = timeit.repeat(workload, number=10, repeat=10)
    mean = sum(times) / len(times)
    std = (sum((t - mean) ** 2 for t in times) / len(times)) ** 0.5
    print(f"Mean: {mean}")
    print(f"Std Dev: {std}")


def _child_once(q):
    try:
        _child_target()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def _run_isolated():
    ctx = multiprocessing.get_context("fork")
    p = ctx.Process(target=_child_once, args=(None,))
    p.start()
    p.join(timeout=300)
    if p.exitcode != 0:
        sys.exit(p.exitcode or 1)


if __name__ == "__main__":
    _run_isolated()
