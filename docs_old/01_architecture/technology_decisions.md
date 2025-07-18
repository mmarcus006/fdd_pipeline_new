# Technology Decisions

This document explains the reasoning behind each technology choice in the FDD Pipeline, including alternatives considered and trade-offs accepted.

## Table of Contents

1. [Package Management](#package-management)
2. [Workflow Orchestration](#workflow-orchestration)
3. [Backend Infrastructure](#backend-infrastructure)
4. [Document Storage](#document-storage)
5. [Web Scraping](#web-scraping)
6. [Document Processing](#document-processing)
7. [LLM Strategy](#llm-strategy)
8. [Structured Output](#structured-output)
9. [Configuration Management](#configuration-management)
10. [Decision Matrix Summary](#decision-matrix-summary)

## Package Management

### Choice: UV (Astral)

**Why UV?**
- **Speed**: 10-100x faster than pip, critical for CI/CD pipelines
- **All-in-one**: Replaces pip, poetry, pipenv, virtualenv, and pyenv
- **Rust-based**: Memory safe and performant
- **Modern**: Built with contemporary Python packaging standards in mind
- **Simplicity**: Single tool instead of multiple dependency managers

**Alternatives Considered:**

| Tool | Pros | Cons | Why Not Chosen |
|------|------|------|----------------|
| Poetry | Mature, lock files, good DX | Slow resolver, complex internals | UV is faster and simpler |
| pip + venv | Standard, universal | No lock files, manual venv management | Lacks modern features |
| pipenv | Lock files, security scanning | Very slow, abandoned/revived project | Performance and stability concerns |
| conda | Scientific packages, non-Python deps | Heavy, different ecosystem | Overkill for our needs |

**Trade-offs Accepted:**
- Newer tool with smaller community
- Requires team to learn new tool
- Not all IDE integrations available yet

**Mitigation:**
- UV is backward compatible with pip
- Can generate requirements.txt for compatibility
- Active development by Astral (ruff creators)

## Workflow Orchestration

### Choice: Prefect

**Why Prefect?**
- **Python-native**: Use decorators, no DSLs or YAML
- **Dynamic workflows**: Create tasks at runtime based on data
- **Superior observability**: Built-in UI shows real-time execution
- **Hybrid execution**: Same code works locally and in cloud
- **Modern architecture**: Built for distributed systems from day one

**Alternatives Considered:**

| Tool | Pros | Cons | Why Not Chosen |
|------|------|------|----------------|
| Airflow | Industry standard, huge community | Complex setup, dated architecture, verbose DAGs | Too heavy for our use case |
| Dagster | Modern, asset-based | Learning curve, over-engineered for pipelines | Complexity without clear benefits |
| Luigi | Simple, Spotify-backed | Limited features, poor UI | Lacks modern orchestration features |
| Temporal | Powerful, language agnostic | Complex, requires separate cluster | Overkill for Python-only pipeline |
| Cron + scripts | Dead simple | No retry logic, monitoring, or failure handling | Too primitive for production |

**Trade-offs Accepted:**
- Smaller community than Airflow
- Prefect 2.0 is relatively new (though stable)
- Some features require Prefect Cloud (free tier sufficient)

**Mitigation:**
- Prefect 1.0 -> 2.0 migration proved team's commitment
- Can self-host Prefect Server
- Active community and responsive support

## Backend Infrastructure

### Choice: Supabase

**Why Supabase?**
- **PostgreSQL foundation**: Battle-tested relational database
- **Batteries included**: Auth, RLS, Edge Functions, Realtime
- **Developer experience**: Instant APIs, great UI, TypeScript client
- **Cost effective**: Generous free tier, predictable scaling costs
- **Open source**: Can self-host if needed

**Alternatives Considered:**

| Tool | Pros | Cons | Why Not Chosen |
|------|------|------|----------------|
| Raw PostgreSQL + API | Full control, no vendor lock-in | Requires building auth, APIs, hosting | Too much undifferentiated work |
| Firebase | Real-time, good mobile SDKs | NoSQL (Firestore), Google lock-in | Need relational data model |
| AWS RDS + Lambda | Mature, scalable | Complex setup, many services to manage | High complexity for small team |
| Planetscale | MySQL, great scaling | MySQL limitations, fewer features | PostgreSQL preferred for JSON support |
| Neon | Serverless Postgres | Newer, fewer features | Supabase more mature |

**Trade-offs Accepted:**
- Some vendor lock-in for Supabase-specific features
- Less control than self-hosted PostgreSQL
- Row-level security has learning curve

**Mitigation:**
- PostgreSQL core means data is portable
- Can use direct PostgreSQL connection if needed
- Supabase is open source and self-hostable

## Document Storage

### Choice: Google Drive

**Why Google Drive?**
- **No file size limits**: Critical for large PDFs (some >100MB)
- **Zero storage cost**: Workspace accounts include unlimited storage
- **Built-in versioning**: Automatic file history
- **Simple API**: Well-documented, Python client available
- **No infrastructure**: Fully managed service

**Alternatives Considered:**

| Tool | Pros | Cons | Why Not Chosen |
|------|------|------|----------------|
| AWS S3 | Industry standard, infinitely scalable | Costs add up, complex permissions | Expensive for large files |
| Local filesystem | Fast, simple | Not distributed, backup complexity | No remote access |
| Cloudflare R2 | S3-compatible, no egress fees | Newer service, less tooling | Google Drive simpler for docs |
| Dropbox | Good sync, simple | API limitations, cost at scale | Less suited for programmatic access |
| SharePoint | Enterprise ready | Complex API, slow, Windows-centric | Poor developer experience |

**Trade-offs Accepted:**
- API rate limits require careful handling
- Not optimized for programmatic access patterns
- Requires Google Workspace account

**Mitigation:**
- Implement exponential backoff for rate limits
- Cache file IDs to minimize API calls
- Use service account for reliability

## Web Scraping

### Choice: Playwright

**Why Playwright?**
- **JavaScript rendering**: Many portals are React/Vue SPAs
- **Modern architecture**: Better than Selenium in every way
- **Auto-waiting**: Smart waits for elements and network
- **Reliability**: Handles flaky sites better
- **Multi-browser**: Can switch browsers if one fails

**Alternatives Considered:**

| Tool | Pros | Cons | Why Not Chosen |
|------|------|------|----------------|
| Selenium | Mature, lots of resources | Slower, flakier, older architecture | Playwright is superior |
| Puppeteer | Good for Chrome | Chrome-only, less Pythonic | Playwright supports more browsers |
| Scrapy | Fast, battle-tested | No JavaScript support | State portals need JS |
| BeautifulSoup + requests | Simple, lightweight | No JavaScript support | Can't handle SPAs |
| Paid APIs (ScraperAPI) | Handles proxies, CAPTCHAs | Expensive, less control | Overkill for government sites |

**Trade-offs Accepted:**
- Heavier than simple HTTP requests
- Requires browser binaries
- More complex deployment

**Mitigation:**
- Use headless mode for efficiency
- Container deployment includes browsers
- Fallback to simpler tools when possible

## Document Processing

### Choice: MinerU (Local Installation)

**Why MinerU Local?**
- **AI-powered**: Best accuracy for complex layouts using deep learning models
- **GPU acceleration**: 10-50x faster than CPU-based alternatives
  - 10,000+ tokens/second on RTX 4090
  - Processes 100-page FDD in ~30 seconds with GPU
  - Same document takes 10-15 minutes on CPU
- **No API costs**: One-time model download, unlimited processing
  - API would cost $0.10-0.50 per page at our volume
  - Processing 1000 FDDs/month = $5,000-25,000 in API costs
  - Local GPU pays for itself in 1-2 months
- **Table detection**: Critical for financial data extraction
  - RapidTable integration for 10x faster table parsing
  - Preserves complex table structures and formatting
  - HTML output maintains relationships
- **Section identification**: Helps split documents accurately
  - Deep learning models trained on document layouts
  - Identifies Item boundaries with 95%+ accuracy
  - Handles variations in FDD formatting
- **Full control**: No rate limits, network latency, or service dependencies
  - Process 100+ documents in parallel with multiple GPUs
  - No API throttling or quota concerns
  - Consistent sub-second latency
- **Privacy**: Documents never leave your infrastructure
  - Critical for confidential franchise data
  - Compliance with data residency requirements
  - No third-party data processing agreements needed
- **Active development**: Rapidly improving with open-source community
  - Monthly updates with performance improvements
  - Strong community support and contributions
  - Roadmap includes even better table/formula extraction

**Why Local Instead of API?**
- **Cost Analysis** (based on 1000 FDDs/month, ~100 pages each):
  - MinerU API: $10,000-50,000/month
  - Adobe Extract API: $30,000+/month  
  - AWS Textract: $15,000/month
  - Local GPU setup: $3,000 one-time (RTX 4090)
- **Performance Benefits**:
  - No network round-trip time (saves 100-500ms per call)
  - Batch processing without API rate limits
  - Can scale horizontally with more GPUs
- **Reliability Advantages**:
  - No downtime from external services
  - No API deprecation concerns
  - Complete control over processing pipeline

**Hardware Requirements:**
- **Minimum**: NVIDIA GTX 1060 (6GB VRAM) or newer
  - Processes documents at ~1-2 pages/second
  - Suitable for <100 FDDs/month
- **Recommended**: NVIDIA RTX 3080/4080 (16GB VRAM)
  - Processes at 5-10 pages/second
  - Handles 500+ FDDs/month comfortably
- **Optimal**: NVIDIA RTX 4090 (24GB VRAM) or A100
  - Maximum throughput of 10-20 pages/second
  - Can process 1000+ FDDs/month
  - Supports larger batch sizes for efficiency

**Alternatives Considered:**

| Tool | Pros | Cons | Why Not Chosen |
|------|------|------|----------------|
| MinerU API | No infrastructure needed | Expensive at scale, network dependency | $5K+/month for our volume |
| Adobe API | Industry leader, high accuracy | Extremely expensive ($0.30+/page), less flexible | Cost prohibitive at scale |
| Textract (AWS) | Good accuracy, AWS integrated | AWS lock-in, high cost ($0.15/page) | MinerU more accurate for our docs |
| Azure Form Recognizer | Good for forms, pre-built models | Not optimized for long documents | FDDs aren't standard forms |
| Tesseract OCR | Free, open source, mature | Poor layout understanding, no GPU | Not smart enough for complex layouts |
| PyPDF2 only | Simple, fast, pure Python | No layout analysis, text only | Need structure detection |
| Unstructured.io | Good accuracy, multiple formats | API costs, rate limits | Similar cost issues as MinerU API |
| Google Document AI | Good OCR, entity extraction | Complex pricing, Google lock-in | Overkill for our use case |

**Trade-offs Accepted:**
- Requires GPU hardware (one-time investment of $1,500-3,000)
- 15GB model download needed (one-time, ~30 minutes)
- More complex deployment than API
- Need to manage GPU resources and drivers
- Responsible for model updates

**Mitigation Strategies:**
- **Hardware Investment**: ROI in 1-2 months vs API costs
- **Fallback to CPU mode**: For development/testing environments
- **PyPDF2 fallback**: Emergency text extraction if MinerU fails
- **Docker deployment**: Includes CUDA, models, all dependencies
- **Batch processing**: Queue system maximizes GPU utilization
- **Model caching**: Download once, share across instances
- **Monitoring**: GPU utilization metrics and alerts

## LLM Strategy

### Choice: Multi-Model Approach (Gemini Primary)

**Why This Strategy?**
- **Cost optimization**: Use cheapest model that works
- **Reliability**: Multiple fallback options
- **Performance**: Local models for simple tasks
- **Quality**: Best model for complex extractions

**Model Selection:**

| Model | Use Case | Why | Cost |
|-------|----------|-----|------|
| Gemini Pro 2.5 | Primary, complex sections | Best accuracy, good price | $0.00375/1K tokens |
| Ollama (Phi-3, Llama3) | Simple tables, structured data | Free, fast, private | $0 (local) |
| OpenAI GPT-4 | Fallback for failures | Highest reliability | $0.03/1K tokens |

**Alternatives Considered:**

| Approach | Pros | Cons | Why Not Chosen |
|----------|------|------|----------------|
| Single model (GPT-4) | Simple, reliable | Expensive, overkill for simple tasks | 10x cost increase |
| All local models | Free, private | Lower accuracy, GPU required | Accuracy matters more |
| Claude | High quality | API availability, cost | Gemini similar quality, better price |
| Fine-tuned model | Perfect for use case | Requires training data, maintenance | Future consideration |

**Trade-offs Accepted:**
- Complexity of managing multiple models
- Different APIs and response formats
- Local infrastructure for Ollama

**Mitigation:**
- Instructor library normalizes outputs
- Fallback chain ensures reliability
- Monitor accuracy metrics per model

## Structured Output

### Choice: Instructor

**Why Instructor?**
- **Pydantic integration**: Type safety and validation
- **Automatic retries**: Fixes extraction errors
- **Multi-provider**: Works with any LLM
- **Battle-tested**: Used in production by many companies
- **Simple API**: Minimal code changes

**Alternatives Considered:**

| Tool | Pros | Cons | Why Not Chosen |
|------|------|------|----------------|
| Manual JSON parsing | Full control | Error-prone, lots of code | Too much boilerplate |
| Langchain | Many features | Heavy, complex, overkill | Don't need agent features |
| Guidance | Interesting approach | Less mature, smaller community | Instructor more proven |
| BAML | Type-safe prompts | New, requires learning | Instructor simpler |
| Custom solution | Tailored to needs | Maintenance burden | Instructor does this well |

**Trade-offs Accepted:**
- Additional dependency
- Abstraction over LLM APIs
- Learning curve for advanced features

**Mitigation:**
- Instructor is lightweight
- Can bypass for simple cases
- Active development and community

## Configuration Management

### Choice: Pydantic Settings

**Why Pydantic Settings?**
- **Type safety**: Catch config errors at startup
- **Environment variables**: 12-factor app compliance
- **Validation**: Ensure config values are valid
- **IDE support**: Autocomplete for all settings
- **Documentation**: Auto-generated from types

**Alternatives Considered:**

| Tool | Pros | Cons | Why Not Chosen |
|------|------|------|----------------|
| python-dotenv only | Simple | No validation or types | Want type safety |
| YAML/JSON files | Human readable | No validation, requires parsing | Less flexible |
| dynaconf | Powerful, multi-format | More complex than needed | Overkill |
| Hydra | Great for ML | Complex, Facebook abandonment risk | Too heavy |
| Environment only | Simple, secure | No local development ease | Want .env files |

**Trade-offs Accepted:**
- Must define settings schema upfront
- Slightly more code than raw env vars
- Team must understand Pydantic

**Mitigation:**
- Pydantic widely adopted
- Clear error messages
- Can generate example .env files

## Decision Matrix Summary

### High-Level Principles Applied

1. **Prefer Boring Technology**: PostgreSQL, Python, REST APIs
2. **Buy vs Build**: Supabase, Google Drive, MinerU API
3. **Developer Experience**: UV, Prefect, Instructor
4. **Cost Consciousness**: Local models, tiered LLM strategy
5. **Production Ready**: All choices proven in production

### Risk Assessment

| Decision | Risk Level | Mitigation Strategy |
|----------|------------|---------------------|
| UV | Low | Backward compatible with pip |
| Prefect | Low | Can revert to cron + scripts |
| Supabase | Medium | PostgreSQL portable, can self-host |
| Google Drive | Low | Standard API, can migrate |
| Playwright | Low | Industry standard for browser automation |
| MinerU Local | Low | Already self-hosted, CPU fallback available |
| Multi-LLM | Low | Multiple providers reduce risk |
| Instructor | Low | Thin wrapper, can remove |
| Pydantic Settings | Low | Standard Python, well supported |

### Future Considerations

**6-Month Horizon:**
- Optimize MinerU GPU utilization with better batching
- Consider adding Redis for caching
- Explore vector database for semantic search
- Evaluate multi-GPU setup for higher throughput

**12-Month Horizon:**
- Fine-tune extraction models for better accuracy
- Investigate moving to S3 if Drive limits hit
- Consider Kubernetes deployment for scaling

**Signs to Revisit Decisions:**
- Google Drive API becomes bottleneck → Move to S3
- LLM costs exceed $1000/month → Invest in fine-tuning
- Team grows beyond 5 → Consider more complex orchestration
- Processing >1000 documents/day → Optimize infrastructure

---

This document is a living record of our technical decisions. As the system evolves and we learn more, we'll update these decisions and their justifications.