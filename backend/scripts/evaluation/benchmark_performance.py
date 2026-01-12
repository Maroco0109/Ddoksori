"""
Performance Benchmarking - Phase 6 Validation

Measures API performance metrics for search and chat endpoints.

Usage:
    conda activate dsr
    python benchmark_performance.py --url http://localhost:8000
"""
import httpx
import time
import argparse
import os
from typing import List, Dict


def benchmark_search(
    api_url: str,
    queries: List[str],
    iterations: int = 100
) -> Dict[str, float]:
    """
    Benchmark /search endpoint performance

    Args:
        api_url: Base URL (e.g., http://localhost:8000)
        queries: List of test queries
        iterations: Number of requests per query

    Returns:
        {
            'p50': 0.234,      # seconds
            'p95': 0.456,
            'p99': 0.678,
            'mean': 0.345,
            'min': 0.123,
            'max': 0.789,
            'throughput': 28.5  # requests/second
        }
    """
    client = httpx.Client(base_url=api_url, timeout=30)
    times = []

    print(f"🔍 Benchmarking /search endpoint...")
    print(f"  Queries: {len(queries)}")
    print(f"  Iterations per query: {iterations}")
    print(f"  Total requests: {len(queries) * iterations}")

    for query in queries:
        for i in range(iterations):
            start = time.time()
            try:
                resp = client.post("/search", json={"query": query, "top_k": 5})
                if resp.status_code == 200:
                    times.append(time.time() - start)
            except Exception as e:
                print(f"  Warning: Request failed: {e}")
                continue

    if not times:
        return {
            'p50': 0, 'p95': 0, 'p99': 0,
            'mean': 0, 'min': 0, 'max': 0,
            'throughput': 0
        }

    times.sort()
    total_time = sum(times)

    return {
        'p50': times[int(len(times) * 0.50)],
        'p95': times[int(len(times) * 0.95)],
        'p99': times[int(len(times) * 0.99)],
        'mean': total_time / len(times),
        'min': times[0],
        'max': times[-1],
        'throughput': len(times) / total_time if total_time > 0 else 0
    }


def benchmark_chat(
    api_url: str,
    queries: List[str],
    iterations: int = 20
) -> Dict[str, float]:
    """
    Benchmark /chat endpoint performance (with LLM)

    Args:
        api_url: Base URL
        queries: List of test queries
        iterations: Number of requests per query

    Returns:
        Performance metrics dictionary
    """
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  OPENAI_API_KEY not configured - skipping chat benchmark")
        return {
            'p50': 0, 'p95': 0, 'p99': 0,
            'mean': 0, 'min': 0, 'max': 0,
            'throughput': 0
        }

    client = httpx.Client(base_url=api_url, timeout=60)
    times = []

    print(f"\n💬 Benchmarking /chat endpoint...")
    print(f"  Queries: {len(queries)}")
    print(f"  Iterations per query: {iterations}")
    print(f"  Total requests: {len(queries) * iterations}")

    for query in queries:
        for i in range(iterations):
            start = time.time()
            try:
                resp = client.post("/chat", json={"message": query, "top_k": 5})
                if resp.status_code == 200:
                    times.append(time.time() - start)
            except Exception as e:
                print(f"  Warning: Request failed: {e}")
                continue

    if not times:
        return {
            'p50': 0, 'p95': 0, 'p99': 0,
            'mean': 0, 'min': 0, 'max': 0,
            'throughput': 0
        }

    times.sort()
    total_time = sum(times)

    return {
        'p50': times[int(len(times) * 0.50)],
        'p95': times[int(len(times) * 0.95)],
        'p99': times[int(len(times) * 0.99)],
        'mean': total_time / len(times),
        'min': times[0],
        'max': times[-1],
        'throughput': len(times) / total_time if total_time > 0 else 0
    }


def print_results(label: str, results: Dict[str, float], target_p95: float = None):
    """
    Print benchmark results

    Args:
        label: Endpoint label (e.g., "Search")
        results: Performance metrics
        target_p95: Target p95 latency for pass/fail
    """
    print(f"\n{'='*60}")
    print(f"📊 {label} Performance Results")
    print(f"{'='*60}")
    print(f"  p50: {results['p50']*1000:7.1f} ms")
    print(f"  p95: {results['p95']*1000:7.1f} ms", end="")

    if target_p95:
        target_ms = target_p95 * 1000
        status = "✅" if results['p95']*1000 < target_ms else "❌"
        print(f"  (target: <{target_ms:.0f}ms) {status}")
    else:
        print()

    print(f"  p99: {results['p99']*1000:7.1f} ms")
    print(f"  mean: {results['mean']*1000:6.1f} ms")
    print(f"  min: {results['min']*1000:7.1f} ms")
    print(f"  max: {results['max']*1000:7.1f} ms")
    print(f"  throughput: {results['throughput']:5.1f} req/s")
    print(f"{'='*60}")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Benchmark API performance"
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="API base URL (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--search-iterations",
        type=int,
        default=50,
        help="Iterations per search query (default: 50)"
    )
    parser.add_argument(
        "--chat-iterations",
        type=int,
        default=10,
        help="Iterations per chat query (default: 10)"
    )
    parser.add_argument(
        "--skip-chat",
        action="store_true",
        help="Skip chat benchmarks (saves API costs)"
    )

    args = parser.parse_args()

    # Test queries (Korean)
    queries = ["환불", "배송지연", "소비자분쟁조정"]

    print(f"\n🚀 API Performance Benchmark")
    print(f"  Base URL: {args.url}")
    print(f"  Search iterations: {args.search_iterations}")
    print(f"  Chat iterations: {args.chat_iterations}")

    # Benchmark search
    search_results = benchmark_search(
        args.url,
        queries,
        iterations=args.search_iterations
    )
    print_results("Search", search_results, target_p95=0.5)  # 500ms target

    # Benchmark chat (if not skipped)
    if not args.skip_chat:
        chat_results = benchmark_chat(
            args.url,
            queries,
            iterations=args.chat_iterations
        )
        print_results("Chat", chat_results, target_p95=5.0)  # 5s target
    else:
        print("\n⏩ Skipping chat benchmark (--skip-chat)")

    print("\n✅ Benchmark complete!")


if __name__ == "__main__":
    main()
