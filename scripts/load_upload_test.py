#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import time
from pathlib import Path
from statistics import mean
from typing import Any

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Concurrent PureLink upload smoke test.")
    parser.add_argument("--count", type=int, default=10, help="Total upload requests.")
    parser.add_argument("--concurrency", type=int, default=5, help="Concurrent upload workers.")
    parser.add_argument("--file", required=True, help="File to upload.")
    parser.add_argument("--knowledge-base-id", type=int, required=True, help="Personal knowledge base id.")
    parser.add_argument("--base-url", default=os.getenv("BASE_URL", "http://localhost:8000"))
    return parser.parse_args()


async def resolve_token(client: httpx.AsyncClient) -> str:
    token = os.getenv("PURELINK_TOKEN")
    if token:
        return token

    identifier = os.getenv("PURELINK_IDENTIFIER") or os.getenv("PURELINK_EMAIL")
    password = os.getenv("PURELINK_PASSWORD")
    if not identifier or not password:
        raise RuntimeError(
            "Set PURELINK_TOKEN, or set PURELINK_IDENTIFIER/PURELINK_EMAIL and PURELINK_PASSWORD.",
        )

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "identifier": identifier,
            "password": password,
        },
    )
    response.raise_for_status()
    return str(response.json()["access_token"])


def classify_response(response: httpx.Response) -> str:
    if response.status_code in {200, 201}:
        return "succeeded"
    try:
        payload: dict[str, Any] = response.json()
    except ValueError:
        return "failed"

    detail = payload.get("detail")
    error_code = detail.get("error_code") if isinstance(detail, dict) else None
    if error_code == "DUPLICATE_DOCUMENT":
        return "duplicates"
    return "failed"


async def upload_once(
    client: httpx.AsyncClient,
    *,
    token: str,
    knowledge_base_id: int,
    file_path: Path,
    index: int,
) -> tuple[str, float]:
    started_at = time.perf_counter()
    headers = {"Authorization": f"Bearer {token}"}
    data = file_path.read_bytes()
    files = {
        "file": (
            f"{file_path.stem}-{index}{file_path.suffix}",
            data,
            "application/octet-stream",
        )
    }
    response = await client.post(
        f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
        headers=headers,
        files=files,
    )
    latency = time.perf_counter() - started_at
    return classify_response(response), latency


async def main() -> None:
    args = parse_args()
    file_path = Path(args.file)
    if not file_path.exists() or not file_path.is_file():
        raise SystemExit(f"File does not exist: {file_path}")

    limits = httpx.Limits(max_connections=args.concurrency, max_keepalive_connections=args.concurrency)
    async with httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=60, limits=limits) as client:
        token = await resolve_token(client)
        semaphore = asyncio.Semaphore(args.concurrency)

        async def bounded_upload(index: int) -> tuple[str, float]:
            async with semaphore:
                return await upload_once(
                    client,
                    token=token,
                    knowledge_base_id=args.knowledge_base_id,
                    file_path=file_path,
                    index=index,
                )

        started_at = time.perf_counter()
        results = await asyncio.gather(*(bounded_upload(index) for index in range(args.count)))
        duration = time.perf_counter() - started_at

    counts = {
        "succeeded": 0,
        "duplicates": 0,
        "failed": 0,
    }
    latencies = []
    for status, latency in results:
        counts[status] = counts.get(status, 0) + 1
        latencies.append(latency)

    print(f"total: {args.count}")
    print(f"succeeded: {counts['succeeded']}")
    print(f"duplicates: {counts['duplicates']}")
    print(f"failed: {counts['failed']}")
    print(f"duration: {duration:.2f}s")
    print(f"average latency: {mean(latencies):.3f}s")


if __name__ == "__main__":
    asyncio.run(main())
