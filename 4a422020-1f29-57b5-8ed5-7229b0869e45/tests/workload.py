import timeit
import statistics
def setup():
    global nx, G
    import networkx as nx
    import random
    random.seed(42)
    # Build a large graph where Kruskal's MST early termination helps
    # The optimization adds early exit after n-1 edges are found
    # This matters most on dense graphs where many edges are skipped
    n = 2000
    G = nx.Graph()
    for i in range(n):
        for j in range(i + 1, min(i + 5, n)):
            G.add_edge(i, j, weight=random.uniform(1.0, 100.0))
    # Add extra random edges for density
    for _ in range(n * 3):
        u = random.randint(0, n - 1)
        v = random.randint(0, n - 1)
        if u != v:
            G.add_edge(u, v, weight=random.uniform(1.0, 100.0))

def workload():
    global nx, G
    # Exercise kruskal_mst_edges via minimum_spanning_tree
    for _ in range(20):
        T = nx.minimum_spanning_tree(G, algorithm='kruskal')
        assert T.number_of_nodes() == G.number_of_nodes()
        assert T.number_of_edges() == G.number_of_nodes() - 1


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
