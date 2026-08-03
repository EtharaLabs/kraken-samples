"""Workload for networkx#6337: Optimize _single_shortest_path function.

The optimization replaces dict-based nextlevel with list, uses G._adj directly
instead of G.adj (skipping AtlasView), and adds early termination when all nodes
have been found. Benefits most on graphs where BFS visits many nodes.
"""
import multiprocessing
import sys
import timeit


def _child_target():
    import networkx as nx

    # Dense graph where BFS visits many nodes
    G_dense = nx.gnp_random_graph(3000, 0.01, seed=42)
    # Grid graph (regular structure, many nodes)
    G_grid = nx.grid_2d_graph(50, 50)  # 2500 nodes

    def workload():
        # single_source_shortest_path exercises _single_shortest_path
        nx.single_source_shortest_path(G_dense, 0)
        nx.single_source_shortest_path(G_dense, 100)
        nx.single_source_shortest_path(G_grid, (0, 0))
        nx.single_source_shortest_path(G_grid, (25, 25))
        # With cutoff (exercises early termination)
        nx.single_source_shortest_path(G_dense, 0, cutoff=3)
        nx.single_source_shortest_path(G_dense, 0, cutoff=5)

    # Warm up
    workload()

    times = timeit.repeat(workload, number=3, repeat=10)
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
