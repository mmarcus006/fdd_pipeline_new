# Product Overview

## FDD Pipeline - Franchise Disclosure Document Processing System

The FDD Pipeline is an automated document intelligence system that transforms unstructured Franchise Disclosure Documents (FDDs) into structured, queryable data. It combines web scraping, AI-powered document analysis, and cloud storage to create a comprehensive franchise intelligence platform.

### Core Purpose
- **Automated Acquisition**: Continuously monitor and download FDDs from state regulatory portals (Minnesota, Wisconsin, with plans for additional states)
- **Intelligent Processing**: Extract structured data from 25 FDD sections using AI/ML techniques
- **Data Quality**: Ensure high accuracy through multi-tier validation (schema, business rules, quality checks)
- **Accessibility**: Provide clean APIs for downstream applications and analytics

### Key Features
- Weekly automated scraping of state franchise portals
- MinerU-powered layout analysis and document segmentation
- Multi-model LLM extraction (Gemini Pro, Ollama, OpenAI) with intelligent routing
- Structured data storage for high-value sections (Items 5, 6, 7, 19, 20, 21)
- Fuzzy matching deduplication to prevent duplicate processing
- Prefect-orchestrated workflows with monitoring and alerting

### Target Metrics
- **Processing Throughput**: 100+ FDDs per day
- **Extraction Accuracy**: >95% for structured sections
- **System Uptime**: 99.5% availability
- **End-to-End Latency**: <10 minutes per document

### Business Value
Transforms manual, time-intensive franchise research into automated, scalable intelligence gathering for franchise analysis, investment decisions, and market research.