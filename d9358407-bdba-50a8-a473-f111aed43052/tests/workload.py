import timeit
import statistics
def setup():
    global nx, graphs
    import networkx as nx
    import random
    random.seed(42)
    # Build several directed graphs to test strongly_connected_components
    # The optimization rewrites Tarjan's SCC algorithm (Tarjan-Zwick 2024)
    # with parallel stacks and early-exit for single-component graphs
    graphs = []
    # Graph 1: Single large SCC (exercises early-exit path)
    n = 2000
    G1 = nx.DiGraph()
    for i in range(n):
        G1.add_edge(i, (i + 1) % n)  # cycle
    for _ in range(n * 2):
        u = random.randint(0, n - 1)
        v = random.randint(0, n - 1)
        if u != v:
            G1.add_edge(u, v)
    graphs.append(G1)
    # Graph 2: Many small SCCs (exercises normal path)
    G2 = nx.DiGraph()
    base = 0
    for _ in range(100):
        size = random.randint(5, 30)
        for i in range(size):
            G2.add_edge(base + i, base + (i + 1) % size)
        # Add some internal random edges
        for _ in range(size):
            u = base + random.randint(0, size - 1)
            v = base + random.randint(0, size - 1)
            if u != v:
                G2.add_edge(u, v)
        base += size
    # Add DAG edges between components
    for i in range(base - 1):
        if random.random() < 0.01:
            G2.add_edge(i, random.randint(i + 1, base - 1))
    graphs.append(G2)
    # Graph 3: Dense graph
    G3 = nx.gnp_random_graph(500, 0.05, directed=True, seed=42)
    graphs.append(G3)

def workload():
    global nx, graphs
    for G in graphs:
        for _ in range(10):
            components = list(nx.strongly_connected_components(G))
            assert len(components) >= 1


# ---- AUTO-GENERATED ISOLATION HARNESS (timeit-in-child, spawn-safe) ----
import statistics as _statistics
import multiprocessing as _mp
import timeit as _timeit

def _child_once(number: int):
    setup_fn = setup
    t = _timeit.Timer(workload, setup=setup_fn)
    return t.timeit(number)

# TOP-LEVEL target: picklable under 'spawn'
def _child_target(q, number):
    try:
        dur = _child_once(number)
        q.put(dur)
    except BaseException:
        import traceback
        traceback.print_exc()
        q.put(None)

def _run_isolated(number: int, repeat: int, start_method: str = "fork"):
    ctx = _mp.get_context(start_method)
    results = []
    for _ in range(repeat):
        q = ctx.Queue()
        p = ctx.Process(target=_child_target, args=(q, number))
        p.start()
        dur = q.get()
        p.join()
        if dur is None or p.exitcode != 0:
            raise RuntimeError("Child run failed—see traceback above.")
        results.append(dur)
    return results

if __name__ == "__main__":
    _number = 1
    _repeat = 10
    runtimes = _run_isolated(_number, _repeat, start_method="fork")
    runtimes_view = runtimes
    print("Mean:", _statistics.mean(runtimes_view))
    print("Std Dev:", _statistics.stdev(runtimes_view) if len(runtimes_view) > 1 else 0.0)
