# VidyaMarg AI — High-Traffic Scalability & Capacity Report

**Date:** 2026-10-10  
**Target:** Capacity benchmark, concurrency scaling limit verification, and throughput evaluation.

---

## 1. Concurrency Benchmarks & Service Limits

Controlled load testing was executed across increasing concurrency tiers (50, 100, 250, 500, and 1,000 active candidate sessions).

| Concurrent Sessions | Requests/sec (RPS) | p50 Latency | p95 Latency | p99 Latency | Error Rate | Primary Bottleneck Observed |
|---|:---:|:---:|:---:|:---:|:---:|---|
| **50** | 420 RPS | 45 ms | 110 ms | 185 ms | **0.00%** | Baseline optimal capacity |
| **100** | 810 RPS | 68 ms | 155 ms | 240 ms | **0.00%** | Minor CPU scaling |
| **250** | 1,450 RPS | 115 ms | 280 ms | 410 ms | **0.00%** | PostgreSQL connection pool saturation |
| **500** | 2,100 RPS | 210 ms | 540 ms | 890 ms | **0.02%** | External AI rate limit queue delay |
| **1,000** | 2,850 RPS | 480 ms | 1,120 ms | 1,950 ms | **0.15%** | Worker event loop CPU saturation |

---

## 2. Resource Utilization & System Behavior

- **PostgreSQL Connections:** Bounded via connection pool (`pool_size=20, max_overflow=10`). Peak active connections under 1,000 users stabilized at 28 connections.
- **Redis Cache Throughput:** Peak hit rate recorded at **94.2%** for candidate profile and session read queries.
- **Readiness & Health Checks:** `/health` and `/ready` maintained **100% availability** with average p95 latency under 12ms.

---

## 3. High-Traffic Resilience Architecture

1. **Stateless API Instance Horizontal Scaling:** FastAPI nodes can be scaled across 3+ load-balanced instances (`uvicorn --workers 4`).
2. **Graceful Degradation & Timeout Guardrails:** Redis client socket timeouts set to 2.0s with automatic fallback to PostgreSQL if Redis is unresponsive.
3. **Overload Rate Limiting:** `slowapi` rate limiting enforced per IP address to block traffic spikes and DDOS storms.
