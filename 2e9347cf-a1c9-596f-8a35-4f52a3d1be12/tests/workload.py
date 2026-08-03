"""Workload for Jinja2 PR #1516: Reduce async overhead in auto_await."""
import statistics as _statistics
import multiprocessing as _mp
import timeit as _timeit

def setup():
    global Environment
    from jinja2 import Environment
    globals()["Environment"] = Environment

def workload():
    Env = globals()["Environment"]
    # Render templates that exercise the auto_await code path
    env = Env(enable_async=True)

    # Create template with multiple expressions (each triggers auto_await)
    tmpl = env.from_string("{% for i in items %}{{ i.name }}: {{ i.value }}\n{% endfor %}")

    import asyncio

    async def render_many():
        items = [{"name": f"item_{i}", "value": i * 100} for i in range(50)]
        for _ in range(100):
            result = await tmpl.render_async(items=items)

    # Run the async rendering
    asyncio.run(render_many())

def _child_once(number):
    setup()
    t = _timeit.Timer(workload)
    return t.timeit(number)

def _child_target(q, number):
    try:
        dur = _child_once(number)
        q.put(dur)
    except BaseException:
        import traceback; traceback.print_exc()
        q.put(None)

def _run_isolated(number, repeat, start_method="fork"):
    ctx = _mp.get_context(start_method)
    results = []
    for _ in range(repeat):
        q = ctx.Queue()
        p = ctx.Process(target=_child_target, args=(q, number))
        p.start()
        dur = q.get()
        p.join()
        if dur is None or p.exitcode != 0:
            raise RuntimeError("Child run failed")
        results.append(dur)
    return results

if __name__ == "__main__":
    _number = 1
    _repeat = 10
    runtimes = _run_isolated(_number, _repeat, start_method="fork")
    print("Mean:", _statistics.mean(runtimes))
    print("Std Dev:", _statistics.stdev(runtimes) if len(runtimes) > 1 else 0.0)
