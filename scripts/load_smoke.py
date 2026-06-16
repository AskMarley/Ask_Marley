import argparse
import concurrent.futures
import time
import urllib.error
import urllib.request

ENDPOINTS = [
    "/",
    "/health",
    "/consumer/chat",
    "/consumer/search",
    "/consumer/clipboard",
    "/provider/dashboard",
    "/admin/dashboard",
]


def hit_endpoint(base_url, path, timeout):
    url = f"{base_url}{path}"
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            status = response.getcode()
            elapsed = (time.perf_counter() - start) * 1000
            return path, status, elapsed, None
    except urllib.error.URLError as exc:
        elapsed = (time.perf_counter() - start) * 1000
        return path, 0, elapsed, str(exc)


def main():
    parser = argparse.ArgumentParser(description="Basic smoke load harness for AskMarley")
    parser.add_argument("--base-url", default="http://127.0.0.1:5000")
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--timeout", type=float, default=4.0)
    args = parser.parse_args()

    jobs = []
    for _ in range(args.rounds):
        for endpoint in ENDPOINTS:
            jobs.append(endpoint)

    successes = 0
    failures = 0
    total_ms = 0.0

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [
            executor.submit(hit_endpoint, args.base_url, endpoint, args.timeout)
            for endpoint in jobs
        ]
        for future in concurrent.futures.as_completed(futures):
            path, status, elapsed, error = future.result()
            total_ms += elapsed
            if 200 <= status < 400:
                successes += 1
                print(f"OK {status} {path} {elapsed:.1f}ms")
            else:
                failures += 1
                print(f"FAIL {status} {path} {elapsed:.1f}ms {error or ''}")

    total_requests = len(jobs)
    avg_ms = total_ms / total_requests if total_requests else 0
    print("\nSummary")
    print(f"Requests: {total_requests}")
    print(f"Success:  {successes}")
    print(f"Failed:   {failures}")
    print(f"Avg ms:   {avg_ms:.1f}")

    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
