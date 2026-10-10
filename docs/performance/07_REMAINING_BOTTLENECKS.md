# VidyaMarg AI — Remaining Bottlenecks & Future Roadmap

**Date:** 2026-10-10  
**Target:** Identify top 5 future optimization opportunities for high-scale growth.

---

## 1. Identified Future Optimization Bottlenecks

| Rank | Area | Description | Impact Level | Proposed Future Solution |
|---|---|---|:---:|---|
| **1** | **LLM Career Agent Latency** | External LLM API calls (Gemini / OpenAI / NVIDIA) take 800ms – 1,800ms for full-text responses. | Medium | Implement streaming HTTP SSE (Server-Sent Events) for immediate token delivery. |
| **2** | **Qdrant Vector Filter Optimization** | High-dimensional candidate skill vector matching during large-batch job recommendations. | Low-Medium | Pre-filter vector searches by `role_category` and location tenant keys before payload scoring. |
| **3** | **PDF Resume Rendering** | Client-side Canvas rendering of multi-page PDF previews in Resume Center. | Low | Implement Web Worker-based background PDF page rasterization. |
| **4** | **Static Asset Edge CDN Caching** | Heavy UI icons and course preview thumbnails served from origin. | Low | Enable Cloudflare / Vercel Edge CDN aggressive caching header for static media. |
| **5** | **Bulk Job Ingestion Crawling** | Batch processing telegram / scraper jobs synchronously in backend background workers. | Low | Offload ingestion parsing into Celery / Redis Queue workers with batch PostgreSQL upserts. |

---

## 2. Summary

All primary user-impacting bottlenecks (page loading waterfalls, un-indexed PostgreSQL queries, dashboard latency) have been successfully resolved, verified, and documented.
