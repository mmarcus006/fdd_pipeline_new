# Import Updates Needed for Module Reorganization

This document lists all Python files that contain imports from moved modules and need to be updated.

## Files with imports from `tasks.*` modules:

### `tasks.minnesota_scraper` -> `scrapers.states.minnesota`
- `workflows/state_configs.py` (line 3)

### `tasks.wisconsin_scraper` -> `scrapers.states.wisconsin`
- `workflows/state_configs.py` (line 4)

### `tasks.web_scraping` -> `scrapers.base.web_scraping`
- `workflows/base_state_flow.py` (lines 12)
- `scrapers/states/minnesota.py` (line 9)
- `scrapers/states/wisconsin.py` (line 8)
- `tasks/document_metadata.py` (line 8)

### `tasks.exceptions` -> `scrapers.base.exceptions`
- `workflows/base_state_flow.py` (line 13)
- `scrapers/states/minnesota.py` (line 13)
- `scrapers/states/wisconsin.py` (line 12)
- `scrapers/base/base_scraper.py` (line 35)
- `processing/extraction/llm_extraction.py` (line 38)
- `tasks/data_storage.py` (line 14)

### `tasks.llm_extraction` -> `processing.extraction.llm_extraction`
- `tasks/document_processing_integration.py` (line 14)

### `tasks.document_segmentation` -> `processing.segmentation.document_segmentation`
- No direct imports found

### `tasks.mineru_processing` -> `processing.mineru.mineru_processing`
- `tasks/document_processing_integration.py` (line 16)

### `tasks.drive_operations` -> `storage.google_drive`
- `processing/segmentation/document_segmentation.py` (line 22)
- `workflows/base_state_flow.py` (line 324)
- `utils/local_drive.py` (line 10)
- `processing/mineru/mineru_processing.py` (line 22)
- `src/api/main.py` (line 300)

### `tasks.schema_validation` -> `validation.schema_validation`
- `workflows/complete_pipeline.py` (line 14)
- `validation/business_rules.py` (line 19)

## Files with imports from `utils.*` modules:

### `utils.scraping_utils` -> `scrapers.utils.scraping_utils`
- `scrapers/states/wisconsin.py` (line 17)
- `scrapers/states/minnesota.py` (line 17)
- `scrapers/base/base_scraper.py` (line 26)
- `tasks/document_metadata.py` (line 131)

### `utils.multimodal_processor` -> `processing.extraction.multimodal_processor`
- `examples/instructor_usage.py` (line 15)

### `utils.pdf_extractor` -> `processing.extraction.pdf_extractor`
- No direct imports found

### `utils.database` -> `storage.database.manager`
- `main.py` (lines 42, 170)
- `workflows/base_state_flow.py` (line 17)
- `workflows/complete_pipeline.py` (line 15)
- `storage/google_drive.py` (line 21)
- `processing/segmentation/document_segmentation.py` (line 28)
- `tasks/data_storage.py` (line 11)
- `validation/schema_validation.py` (line 31)
- `validation/business_rules.py` (line 26)
- `utils/entity_operations.py` (line 15)
- `utils/document_lineage.py` (line 15)
- `src/api/main.py` (line 26)
- `scripts/monitoring.py` (line 21)
- `scripts/health_check.py` (line 20)
- `scripts/orchestrate_workflow.py` (line 27)
- `scripts/check_config.py` (line 16)

### `utils.validation` -> `validation.validation_utils`
- No direct imports found

## Files with imports from `flows.*` modules:

### `flows.base_state_flow` -> `workflows.base_state_flow`
- `main.py` (lines 62, 293)
- `workflows/state_configs.py` (line 5)
- `workflows/complete_pipeline.py` (line 11)
- `scripts/deploy_state_flows.py` (line 25)
- `scripts/orchestrate_workflow.py` (line 29)

### `flows.state_configs` -> `workflows.state_configs`
- `main.py` (lines 63, 294)
- `workflows/complete_pipeline.py` (line 12)
- `scripts/deploy_state_flows.py` (line 26)
- `scripts/orchestrate_workflow.py` (line 30)

### `flows.complete_pipeline` -> `workflows.complete_pipeline`
- `flows/__init__.py` (line 3) - imports all modules

### `flows.process_single_pdf` -> `workflows.process_single_pdf`
- `main.py` (line 103)
- `workflows/complete_pipeline.py` (line 13)
- `scripts/orchestrate_workflow.py` (line 31)
- `flows/__init__.py` (line 3)

## Files with imports from `src.*` modules:

### `src.processing.enhanced_fdd_section_detector_claude` -> `processing.segmentation.enhanced_fdd_section_detector_claude`
- `utils/fdd_section_detector_integration.py` (line 16)
- `processing/segmentation/enhanced_detector.py` (line 8)

### `src.processing.section_identifier` -> `processing.segmentation.section_identifier`
- `archive/identify_fdd_sections.py` (line 3)

### `src.MinerU.mineru_web_api` -> `processing.mineru.mineru_web_api`
- No direct imports found

## Summary

Total files needing updates: **31 files**

Most common import updates needed:
1. `utils.database` -> `storage.database.manager` (15 files)
2. `tasks.exceptions` -> `scrapers.base.exceptions` (6 files)
3. `tasks.drive_operations` -> `storage.google_drive` (5 files)
4. `flows.base_state_flow` -> `workflows.base_state_flow` (5 files)
5. `flows.state_configs` -> `workflows.state_configs` (4 files)

## Notes

- Some imports appear to be conditional (inside functions) and may need special attention
- The `flows/__init__.py` file imports all modules from the flows package and may need restructuring
- Some files in the `archive/` directory reference old module paths but may not need updating if they're not actively used