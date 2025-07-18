"""
Enhanced FDD Section Detection using MinerU JSON Output

This module provides advanced section boundary detection for Franchise Disclosure Documents
using multiple approaches including title element analysis, cosine similarity, fuzzy matching,
and validation rules.

Author: Claude Code Assistant
Created: 2025-01-18
"""

import re
import json
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
import logging

# Third-party imports (use latest documentation patterns)
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from rapidfuzz import fuzz
import numpy as np

# Project imports
from models.document_models import SectionBoundary


logger = logging.getLogger(__name__)


@dataclass
class FDDSectionCandidate:
    """Represents a potential FDD section boundary candidate"""
    item_no: int
    item_name: str
    page_idx: int  # 0-indexed page from MinerU
    page_number: int  # 1-indexed actual page number
    confidence: float
    text_content: str
    bbox: List[float]  # [x0, y0, x1, y1] bounding box
    detection_method: str  # 'title', 'fuzzy', 'pattern', 'cosine'
    element_type: str  # 'title', 'text', etc.
    
    def __post_init__(self):
        """Ensure page_number is properly calculated"""
        if self.page_number == 0:
            self.page_number = self.page_idx + 1


class EnhancedFDDSectionDetector:
    """
    Enhanced FDD Section Detection using MinerU JSON output with multiple detection strategies.
    
    Uses COSTAR Framework approach:
    - Context: FDD documents follow FTC Rule 436 with 23 standard items plus intro/appendix
    - Objective: Accurately determine start/end page numbers for each section
    - Situation: MinerU provides structured JSON with layout analysis including title elements
    - Task: Multi-pronged detection using title attributes, similarity matching, and validation
    - Action: Implement detection algorithms with confidence scoring and validation rules
    - Result: Precise section boundaries with overlap handling for comprehensive extraction
    """
    
    # Official FTC Rule 436 section headers (exact regulatory language)
    STANDARD_FDD_SECTIONS = {
        0: "Cover/Introduction/Table of Contents",
        1: "The Franchisor, and any Parents, Predecessors, and Affiliates", 
        2: "Business Experience",
        3: "Litigation", 
        4: "Bankruptcy",
        5: "Initial Fees",
        6: "Other Fees", 
        7: "Estimated Initial Investment",
        8: "Restrictions on Sources of Products and Services",
        9: "Franchisee's Obligations",
        10: "Financing", 
        11: "Franchisor's Assistance, Advertising, Computer Systems, and Training",
        12: "Territory",
        13: "Trademarks",
        14: "Patents, Copyrights, and Proprietary Information", 
        15: "Obligation to Participate in the Actual Operation of the Franchise Business",
        16: "Restrictions on What the Franchisee May Sell",
        17: "Renewal, Termination, Transfer, and Dispute Resolution", 
        18: "Public Figures",
        19: "Financial Performance Representations",
        20: "Outlets and Franchisee Information", 
        21: "Financial Statements",
        22: "Contracts", 
        23: "Receipts",
        24: "Appendix/Exhibits"
    }
    
    # Alternative phrasings and common variations
    SECTION_VARIATIONS = {
        1: ["The Franchisor", "Franchisor and Parents", "The Franchisor and Any Parents"],
        5: ["Initial Fees", "Initial Fee", "Franchise Fee"],
        6: ["Other Fees", "Ongoing Fees", "Additional Fees"],
        7: ["Estimated Initial Investment", "Initial Investment", "Total Investment"],
        11: ["Franchisor's Assistance", "Training", "Support"],
        17: ["Renewal, Termination", "Contract Terms"],
        19: ["Financial Performance", "Earnings Claims", "Financial Performance Representations"],
        20: ["Outlets and Franchisee Information", "Outlet Information", "System Information"],
        21: ["Financial Statements", "Financials"]
    }
    
    def __init__(self, confidence_threshold: float = 0.5, min_fuzzy_score: int = 75):
        """
        Initialize the enhanced section detector.
        
        Args:
            confidence_threshold: Minimum confidence score for section detection
            min_fuzzy_score: Minimum fuzzy matching score (0-100)
        """
        self.confidence_threshold = confidence_threshold
        self.min_fuzzy_score = min_fuzzy_score
        self.vectorizer = TfidfVectorizer(
            stop_words='english',
            ngram_range=(1, 3),
            max_features=1000
        )
        self._reference_vectors = None
        self._prepare_reference_vectors()
        
    def _prepare_reference_vectors(self):
        """Prepare TF-IDF vectors for standard section headers for cosine similarity"""
        # Combine standard headers with variations
        all_headers = []
        for item_no, header in self.STANDARD_FDD_SECTIONS.items():
            all_headers.append(header)
            if item_no in self.SECTION_VARIATIONS:
                all_headers.extend(self.SECTION_VARIATIONS[item_no])
        
        # Fit vectorizer on all possible headers
        self._reference_vectors = self.vectorizer.fit_transform(all_headers)
        logger.info(f"Prepared reference vectors for {len(all_headers)} section headers")
        
    def detect_sections_from_mineru_json(
        self, 
        mineru_json_path: str,
        total_pages: Optional[int] = None
    ) -> List[SectionBoundary]:
        """
        Main entry point for section detection using MinerU JSON output.
        
        Args:
            mineru_json_path: Path to MinerU layout.json file
            total_pages: Total pages in document (for validation)
            
        Returns:
            List of detected section boundaries with page numbers
        """
        logger.info(f"Starting enhanced section detection for {mineru_json_path}")
        
        # Load and parse MinerU JSON
        mineru_data = self._load_mineru_json(mineru_json_path)
        if not mineru_data:
            logger.error("Failed to load MinerU JSON data")
            return []
            
        # Extract candidates using multiple methods
        candidates = self._extract_section_candidates(mineru_data)
        logger.info(f"Found {len(candidates)} section candidates")
        
        # Log candidate summary
        if logger.isEnabledFor(logging.DEBUG):
            candidate_summary = {}
            for c in candidates:
                if c.item_no not in candidate_summary:
                    candidate_summary[c.item_no] = []
                candidate_summary[c.item_no].append((c.page_number, c.confidence, c.detection_method))
            
            logger.debug("=== CANDIDATE SUMMARY ===")
            for item_no in sorted(candidate_summary.keys()):
                logger.debug(f"Item {item_no:2d}: {len(candidate_summary[item_no])} candidates")
                for page, conf, method in sorted(candidate_summary[item_no])[:3]:  # Top 3
                    logger.debug(f"  Page {page:3d} | Conf: {conf:.2f} | Method: {method}")
        
        # Apply validation rules and resolve conflicts
        validated_sections = self._validate_and_resolve_candidates(candidates, total_pages)
        logger.info(f"Validated {len(validated_sections)} final sections")
        
        # Log final section assignments
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("\n=== FINAL SECTION ASSIGNMENTS ===")
            for section in validated_sections:
                logger.debug(f"Item {section.item_no:2d}: Page {section.page_number:3d} | "
                           f"Conf: {section.confidence:.2f} | Method: {section.detection_method} | "
                           f"Text: '{section.text_content[:40]}...'")
            logger.debug("=" * 50)
        
        # Convert to SectionBoundary objects
        section_boundaries = self._create_section_boundaries(validated_sections, total_pages)
        
        return section_boundaries
        
    def _load_mineru_json(self, json_path: str) -> Optional[Dict[str, Any]]:
        """Load and validate MinerU JSON structure"""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            if 'pdf_info' not in data:
                logger.error("Invalid MinerU JSON: missing 'pdf_info' key")
                return None
                
            logger.info(f"Loaded MinerU JSON with {len(data['pdf_info'])} pages")
            return data
            
        except (json.JSONDecodeError, FileNotFoundError, KeyError) as e:
            logger.error(f"Error loading MinerU JSON: {e}")
            return None
            
    def _extract_section_candidates(self, mineru_data: Dict[str, Any]) -> List[FDDSectionCandidate]:
        """
        Extract section candidates using multiple detection methods.
        
        Five Whys Analysis:
        1. Why multiple methods? - Different PDF layouts may emphasize sections differently
        2. Why title elements first? - MinerU specifically identifies these as headers
        3. Why fuzzy matching? - Handles OCR errors and formatting variations
        4. Why cosine similarity? - Captures semantic similarity beyond exact matches
        5. Why pattern matching? - Ensures "Item X" patterns aren't missed
        """
        candidates = []
        total_pages = len(mineru_data['pdf_info'])
        
        # Define likely appendix threshold (last 20% of document)
        appendix_threshold = max(1, int(total_pages * 0.8))
        
        for page_data in mineru_data['pdf_info']:
            page_idx = page_data['page_idx']
            page_number = page_idx + 1
            
            # Method 1: Title element detection (highest priority)
            title_candidates = self._detect_from_title_elements(page_data, page_idx)
            candidates.extend(title_candidates)
            
            # Method 2: Pattern matching for "Item X" text
            pattern_candidates = self._detect_from_patterns(page_data, page_idx)
            candidates.extend(pattern_candidates)
            
            # Method 3: Fuzzy matching against standard headers (skip likely appendix pages)
            if page_number <= appendix_threshold:
                fuzzy_candidates = self._detect_from_fuzzy_matching(page_data, page_idx)
                candidates.extend(fuzzy_candidates)
            
            # Method 4: Cosine similarity for semantic matching (skip likely appendix pages)
            if page_number <= appendix_threshold:
                cosine_candidates = self._detect_from_cosine_similarity(page_data, page_idx)
                candidates.extend(cosine_candidates)
            
        # Filter and sort candidates
        candidates = self._filter_candidates(candidates, total_pages)
        
        # Sort by page and confidence
        candidates.sort(key=lambda x: (x.page_idx, -x.confidence))
        
        logger.info(
            f"Extracted candidates by method: "
            f"title={len([c for c in candidates if c.detection_method == 'title'])}, "
            f"pattern={len([c for c in candidates if c.detection_method == 'pattern'])}, "
            f"fuzzy={len([c for c in candidates if c.detection_method == 'fuzzy'])}, "
            f"cosine={len([c for c in candidates if c.detection_method == 'cosine'])}"
        )
        
        return candidates
        
    def _filter_candidates(self, candidates: List[FDDSectionCandidate], total_pages: int) -> List[FDDSectionCandidate]:
        """Filter candidates to remove duplicates and improve quality"""
        if not candidates:
            return candidates
            
        # Group candidates by item number and page to remove near-duplicates
        filtered = []
        seen_combinations = set()
        
        for candidate in candidates:
            # Create a key to identify similar candidates
            key = (candidate.item_no, candidate.page_number)
            
            if key not in seen_combinations:
                seen_combinations.add(key)
                filtered.append(candidate)
            else:
                # If we've seen this item/page combo, only keep if this one has higher confidence
                existing_idx = None
                for i, existing in enumerate(filtered):
                    if (existing.item_no == candidate.item_no and 
                        existing.page_number == candidate.page_number):
                        existing_idx = i
                        break
                        
                if existing_idx is not None and candidate.confidence > filtered[existing_idx].confidence:
                    filtered[existing_idx] = candidate
        
        logger.info(f"Filtered {len(candidates)} candidates down to {len(filtered)}")
        return filtered
        
    def _detect_from_title_elements(
        self, 
        page_data: Dict[str, Any], 
        page_idx: int
    ) -> List[FDDSectionCandidate]:
        """Detect sections from MinerU title elements - highest confidence method"""
        candidates = []
        page_number = page_idx + 1
        
        logger.debug(f"Processing title elements on page {page_number}")
        
        title_count = 0
        for para_block in page_data.get('para_blocks', []):
            if para_block.get('type') == 'title':
                title_count += 1
                
            if para_block.get('type') != 'title':
                continue
                
            # Extract text content from title
            text_content = self._extract_text_from_block(para_block)
            logger.debug(f"  Found title element: '{text_content[:100]}...' on page {page_number}")
            
            if not text_content:
                logger.debug(f"    -> Skipped: empty text content")
                continue
                
            # Check for Item patterns
            item_match = self._match_item_pattern(text_content)
            if item_match:
                item_no, item_name = item_match
                logger.debug(f"    -> MATCHED Item {item_no}: '{item_name}' (confidence: 0.95)")
                
                candidate = FDDSectionCandidate(
                    item_no=item_no,
                    item_name=item_name,
                    page_idx=page_idx,
                    page_number=page_idx + 1,
                    confidence=0.95,  # High confidence for title elements
                    text_content=text_content,
                    bbox=para_block.get('bbox', [0, 0, 0, 0]),
                    detection_method='title',
                    element_type='title'
                )
                candidates.append(candidate)
            else:
                logger.debug(f"    -> No item pattern match for: '{text_content}'")
                
        logger.debug(f"Page {page_number}: Found {title_count} title elements, {len(candidates)} title candidates")
        return candidates
        
    def _detect_from_patterns(
        self, 
        page_data: Dict[str, Any], 
        page_idx: int
    ) -> List[FDDSectionCandidate]:
        """Detect using regex patterns for 'Item X' text"""
        candidates = []
        
        for para_block in page_data.get('para_blocks', []):
            text_content = self._extract_text_from_block(para_block)
            if not text_content:
                continue
                
            # Use comprehensive Item pattern matching
            item_matches = self._find_all_item_patterns(text_content)
            
            for item_no, item_text in item_matches:
                # Validate item number is in expected range
                if 0 <= item_no <= 24:
                    candidate = FDDSectionCandidate(
                        item_no=item_no,
                        item_name=self.STANDARD_FDD_SECTIONS.get(item_no, f"Item {item_no}"),
                        page_idx=page_idx,
                        page_number=page_idx + 1,
                        confidence=0.8,  # Good confidence for pattern matches
                        text_content=item_text,
                        bbox=para_block.get('bbox', [0, 0, 0, 0]),
                        detection_method='pattern',
                        element_type=para_block.get('type', 'text')
                    )
                    candidates.append(candidate)
                    
        return candidates
        
    def _detect_from_fuzzy_matching(
        self, 
        page_data: Dict[str, Any], 
        page_idx: int
    ) -> List[FDDSectionCandidate]:
        """Detect using fuzzy string matching against standard headers"""
        candidates = []
        page_number = page_idx + 1
        
        logger.debug(f"Processing fuzzy matching on page {page_number}")
        
        blocks_processed = 0
        header_like_count = 0
        fuzzy_matches = 0
        
        for para_block in page_data.get('para_blocks', []):
            blocks_processed += 1
            text_content = self._extract_text_from_block(para_block)
            
            if not text_content or len(text_content) < 5:
                continue
                
            # Only consider text that looks like a section header
            if not self._looks_like_section_header(text_content):
                logger.debug(f"  Text doesn't look like header: '{text_content[:50]}...'")
                continue
                
            header_like_count += 1
            logger.debug(f"  Checking header-like text: '{text_content[:80]}...'")
                
            # Check against all standard headers
            best_match = self._find_best_fuzzy_match(text_content)
            
            if best_match and best_match[1] >= self.min_fuzzy_score:
                item_no, score, matched_header = best_match
                logger.debug(f"    -> Fuzzy match: Item {item_no} (score: {score}) matched '{matched_header}'")
                
                # Additional validation: check if the match makes sense
                if not self._validate_section_match(item_no, text_content):
                    logger.debug(f"    -> REJECTED: Failed section validation for Item {item_no}")
                    continue
                
                fuzzy_matches += 1
                logger.debug(f"    -> ACCEPTED: Item {item_no} fuzzy match (confidence: {score/100.0:.2f})")
                
                candidate = FDDSectionCandidate(
                    item_no=item_no,
                    item_name=matched_header,
                    page_idx=page_idx,
                    page_number=page_idx + 1,
                    confidence=score / 100.0,  # Convert to 0-1 scale
                    text_content=text_content,
                    bbox=para_block.get('bbox', [0, 0, 0, 0]),
                    detection_method='fuzzy',
                    element_type=para_block.get('type', 'text')
                )
                candidates.append(candidate)
            else:
                if best_match:
                    logger.debug(f"    -> Score too low: {best_match[1]} < {self.min_fuzzy_score}")
                else:
                    logger.debug(f"    -> No fuzzy match found")
                
        logger.debug(f"Page {page_number}: Processed {blocks_processed} blocks, {header_like_count} header-like, {fuzzy_matches} fuzzy matches")
        return candidates
        
    def _detect_from_cosine_similarity(
        self, 
        page_data: Dict[str, Any], 
        page_idx: int
    ) -> List[FDDSectionCandidate]:
        """Detect using cosine similarity for semantic matching"""
        candidates = []
        
        if self._reference_vectors is None:
            return candidates
            
        for para_block in page_data.get('para_blocks', []):
            text_content = self._extract_text_from_block(para_block)
            if not text_content or len(text_content) < 10:
                continue
                
            # Vectorize the text
            try:
                text_vector = self.vectorizer.transform([text_content])
                similarities = cosine_similarity(text_vector, self._reference_vectors)[0]
                
                # Find best match above threshold
                max_sim_idx = np.argmax(similarities)
                max_similarity = similarities[max_sim_idx]
                
                if max_similarity >= self.confidence_threshold:
                    # Map back to item number (approximate - would need refinement)
                    item_no = max_sim_idx % 25  # Rough mapping
                    
                    # Ensure item_no is a standard Python int for compatibility
                    item_no_int = int(item_no)
                    item_name = self.STANDARD_FDD_SECTIONS.get(item_no_int, f"Item {item_no_int}")
                    candidate = FDDSectionCandidate(
                        item_no=item_no_int,
                        item_name=item_name,
                        page_idx=page_idx,
                        page_number=page_idx + 1,
                        confidence=float(max_similarity),
                        text_content=text_content,
                        bbox=para_block.get('bbox', [0, 0, 0, 0]),
                        detection_method='cosine',
                        element_type=para_block.get('type', 'text')
                    )
                    candidates.append(candidate)
                    
            except Exception as e:
                logger.warning(f"Cosine similarity failed for text: {e}")
                continue
                
        return candidates
        
    def _extract_text_from_block(self, para_block: Dict[str, Any]) -> str:
        """Extract text content from a MinerU paragraph block"""
        text_parts = []
        
        # Handle both direct lines and nested blocks
        for lines_source in [para_block.get('lines', []), 
                           *[block.get('lines', []) for block in para_block.get('blocks', [])]]:
            for line in lines_source:
                for span in line.get('spans', []):
                    content = span.get('content', '').strip()
                    if content:
                        text_parts.append(content)
                        
        return ' '.join(text_parts).strip()
        
    def _match_item_pattern(self, text: str) -> Optional[Tuple[int, str]]:
        """Match text against Item patterns and return item number and name"""
        # Primary pattern: "Item X" followed by description
        item_pattern = re.compile(r'\bItem\s+(\d+)\b\s*[:\-]?\s*(.*)', re.IGNORECASE)
        match = item_pattern.search(text)
        
        if match:
            item_no = int(match.group(1))
            item_name = match.group(2).strip()
            
            # Validate item number range
            if 0 <= item_no <= 24:
                # Use standard name if description is too short
                if len(item_name) < 5:
                    item_name = self.STANDARD_FDD_SECTIONS.get(item_no, f"Item {item_no}")
                return item_no, item_name
                
        return None
        
    def _find_all_item_patterns(self, text: str) -> List[Tuple[int, str]]:
        """Find all Item patterns in text (handles table of contents)"""
        patterns = []
        
        # Multiple regex patterns for different formats
        item_patterns = [
            r'\bItem\s+(\d+)\b[:\-]?\s*([^.]*?)(?:\s+\d+\s*$|\n|$)',  # Standard format
            r'\b(\d+)\.\s+(.*?)(?=\s+\d+\s*$|\n|$)',  # Numbered list format  
            r'\bItem\s+(\d+)\s+([A-Z][^.]*)',  # Title case format
        ]
        
        for pattern in item_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
                item_no = int(match.group(1))
                item_text = match.group(2).strip()
                
                if 0 <= item_no <= 24 and len(item_text) > 3:
                    patterns.append((item_no, item_text))
                    
        return patterns
        
    def _find_best_fuzzy_match(self, text: str) -> Optional[Tuple[int, float, str]]:
        """Find best fuzzy match against standard headers with improved filtering"""
        best_score = 0
        best_match = None
        
        # Reject very long text that's likely not a section header
        if len(text) > 200:
            return None
            
        # Reject text that looks like legal boilerplate (common false positives)
        text_lower = text.lower()
        boilerplate_phrases = [
            "the franchisor is",
            "this disclosure document",
            "if we offer you",
            "if we do not deliver",
            "receipt (your copy)",
            "receipt (copy - submit",
            "list of administrators",
            "agents for service"
        ]
        
        if any(phrase in text_lower for phrase in boilerplate_phrases):
            return None
        
        # Check against standard headers and variations
        for item_no, header in self.STANDARD_FDD_SECTIONS.items():
            score = fuzz.partial_ratio(text.lower(), header.lower())
            if score > best_score:
                best_score = score
                best_match = (item_no, score, header)
                
            # Check variations if they exist
            if item_no in self.SECTION_VARIATIONS:
                for variation in self.SECTION_VARIATIONS[item_no]:
                    score = fuzz.partial_ratio(text.lower(), variation.lower())
                    if score > best_score:
                        best_score = score
                        best_match = (item_no, score, variation)
                        
        return best_match if best_score >= self.min_fuzzy_score else None
        
    def _looks_like_section_header(self, text: str) -> bool:
        """Check if text looks like a section header rather than body text"""
        text_upper = text.upper().strip()
        
        # Must be reasonably short to be a header
        if len(text) > 150:
            logger.debug(f"      Header check FAILED: Too long ({len(text)} chars) - '{text[:50]}...'")
            return False
        
        # Headers typically are in all caps or title case
        if text_upper == text or text.istitle():
            logger.debug(f"      Header check PASSED: All caps or title case - '{text[:50]}...'")
            return True
            
        # Look for "Item X" patterns
        if "ITEM " in text_upper and any(char.isdigit() for char in text):
            logger.debug(f"      Header check PASSED: Contains 'Item X' pattern - '{text[:50]}...'")
            return True
            
        # Look for common header patterns
        header_patterns = [
            "INITIAL FEES",
            "OTHER FEES", 
            "ESTIMATED INITIAL INVESTMENT",
            "BUSINESS EXPERIENCE",
            "LITIGATION",
            "BANKRUPTCY",
            "FINANCING",
            "TERRITORY",
            "TRADEMARKS",
            "PATENTS",
            "CONTRACTS",
            "RECEIPTS",
            "FRANCHISEE'S OBLIGATIONS",
            "FINANCIAL PERFORMANCE",
            "FINANCIAL STATEMENTS",
            "RESTRICTIONS ON",
            "FRANCHISOR'S ASSISTANCE",
            "PUBLIC FIGURES",
            "OUTLETS AND FRANCHISE"
        ]
        
        # If it contains a header pattern and is short, likely a header
        matched_patterns = [p for p in header_patterns if p in text_upper]
        if matched_patterns and len(text) < 100:
            logger.debug(f"      Header check PASSED: Contains pattern '{matched_patterns[0]}' - '{text[:50]}...'")
            return True
            
        logger.debug(f"      Header check FAILED: No pattern match - '{text[:50]}...'")
        return False
        
    def _validate_section_match(self, item_no: int, text: str) -> bool:
        """Validate that the detected text actually matches the expected section content"""
        text_lower = text.lower()
        
        logger.debug(f"      Validating Item {item_no} match: '{text[:60]}...'")
        
        # Item-specific validation rules to prevent obvious mismatches
        validation_rules = {
            8: ["restrictions", "sources", "products", "services"],  # Item 8 should be about restrictions
            5: ["initial", "fee", "franchise fee"],  # Item 5 should mention initial/franchise fees
            6: ["other", "fee", "ongoing", "royalty"],  # Item 6 should mention other fees
            7: ["investment", "initial", "estimated"],  # Item 7 should mention investment
            21: ["financial", "statement", "audit"],  # Item 21 should mention financial statements
            19: ["financial", "performance", "representation", "earnings"],  # Item 19 FPR
        }
        
        if item_no in validation_rules:
            required_keywords = validation_rules[item_no]
            found_keywords = [k for k in required_keywords if k in text_lower]
            
            # At least one required keyword must be present
            if not found_keywords:
                logger.debug(f"        Validation FAILED: Item {item_no} missing required keywords {required_keywords}")
                return False
            else:
                logger.debug(f"        Validation check 1 PASSED: Item {item_no} found keywords {found_keywords}")
                
        # Reject obvious mismatches
        wrong_matches = {
            8: ["financial statements", "audited", "balance sheet"],  # Item 8 is NOT about financials
            5: ["adjusted gross revenue", "note 2:", "royalty fee"],  # Item 5 is NOT about ongoing fees
        }
        
        if item_no in wrong_matches:
            wrong_keywords = wrong_matches[item_no]
            found_wrong = [k for k in wrong_keywords if k in text_lower]
            if found_wrong:
                logger.debug(f"        Validation FAILED: Item {item_no} contains wrong keywords {found_wrong}")
                return False
                
        logger.debug(f"        Validation PASSED: Item {item_no} is valid match")
        return True
        
    def _is_exact_section_header(self, text: str, item_no: int) -> bool:
        """Check if text is an exact or near-exact match for a standard section header"""
        text_upper = text.upper().strip()
        
        # Get the standard section name for this item
        standard_name = self.STANDARD_FDD_SECTIONS.get(item_no, "").upper()
        
        # Check for exact match
        if standard_name in text_upper:
            return True
            
        # Check for variations
        if item_no in self.SECTION_VARIATIONS:
            for variation in self.SECTION_VARIATIONS[item_no]:
                if variation.upper() in text_upper:
                    return True
                    
        # Check for specific exact header patterns
        exact_headers = {
            5: ["INITIAL FEES", "INITIAL FEE"],
            6: ["OTHER FEES"], 
            7: ["ESTIMATED INITIAL INVESTMENT"],
            8: ["RESTRICTIONS ON SOURCES OF PRODUCTS AND SERVICES"],
            9: ["FRANCHISEE'S OBLIGATIONS"],
            10: ["FINANCING"],
            11: ["FRANCHISOR'S ASSISTANCE", "FRANCHISOR'S ASSISTANCE, ADVERTISING, COMPUTER SYSTEMS AND TRAINING"],
            12: ["TERRITORY"],
            13: ["TRADEMARKS"],
            14: ["PATENTS, COPYRIGHTS, AND PROPRIETARY INFORMATION"],
            19: ["FINANCIAL PERFORMANCE REPRESENTATIONS"],
            21: ["FINANCIAL STATEMENTS"]
        }
        
        if item_no in exact_headers:
            for header in exact_headers[item_no]:
                if header in text_upper:
                    return True
                    
        return False
        
    def _validate_and_resolve_candidates(
        self, 
        candidates: List[FDDSectionCandidate],
        total_pages: Optional[int] = None
    ) -> List[FDDSectionCandidate]:
        """
        Apply validation rules to build sections sequentially with strict ordering.
        
        Key Principles:
        1. Build sections in sequential order (0→1→2→...→24)
        2. NEVER allow sequential ordering violations
        3. Force Item 0 to start on page 1
        4. For each item, find earliest valid candidate AFTER previous section
        5. Interpolate missing sections respecting sequential constraints
        """
        if not candidates:
            return self._create_fallback_sections(total_pages or 75)
            
        # Sort all candidates by page number for sequential processing
        candidates.sort(key=lambda x: x.page_number)
        
        # Group candidates by item number for easy lookup
        by_item = {}
        for candidate in candidates:
            if candidate.item_no not in by_item:
                by_item[candidate.item_no] = []
            by_item[candidate.item_no].append(candidate)
            
        # Sort candidates within each item by quality (prefer earlier pages when confidence is similar)
        method_priority = {'title': 4, 'pattern': 3, 'fuzzy': 2, 'cosine': 1}
        for item_no in by_item:
            by_item[item_no].sort(
                key=lambda x: (
                    x.confidence, 
                    method_priority.get(x.detection_method, 0),
                    -x.page_number  # Prefer earlier pages (negative for reverse sort)
                ),
                reverse=True
            )
        
        # Build sections sequentially with reasonableness checks
        final_sections = []
        current_min_page = 1  # Start from page 1
        
        logger.debug("=== SEQUENTIAL SECTION BUILDING ===")
        
        for item_no in range(25):  # Items 0-24
            logger.debug(f"\nProcessing Item {item_no} (current min_page: {current_min_page})")
            
            # Show available candidates for this item
            if item_no in by_item:
                logger.debug(f"  Available candidates for Item {item_no}:")
                for i, candidate in enumerate(by_item[item_no][:3]):  # Show top 3
                    valid_marker = "✓" if candidate.page_number >= current_min_page else "✗"
                    logger.debug(f"    {i+1}. {valid_marker} Page {candidate.page_number} | "
                               f"Conf: {candidate.confidence:.2f} | Method: {candidate.detection_method} | "
                               f"Text: '{candidate.text_content[:40]}...'")
            else:
                logger.debug(f"  No candidates found for Item {item_no}")
            
            section = self._find_sequential_section(
                item_no, by_item, current_min_page, total_pages
            )
            
            # Force Item 0 to start on page 1
            if item_no == 0:
                logger.debug(f"  FORCING Item 0 to page 1 (was: {section.page_number})")
                section.page_number = 1
                section.page_idx = 0
                current_min_page = 2  # Next section starts at page 2 minimum
            else:
                # Update minimum page for next section
                # Don't increment by 1 - allow sections to potentially start on same page
                prev_min_page = current_min_page
                current_min_page = section.page_number
                logger.debug(f"  Updated min_page: {prev_min_page} -> {current_min_page}")
                
            logger.debug(f"  FINAL: Item {item_no} assigned to page {section.page_number} "
                        f"(method: {section.detection_method}, conf: {section.confidence:.2f})")
            final_sections.append(section)
                
        return final_sections
        
        
    def _has_exact_item_pattern(self, text: str, item_no: int) -> bool:
        """
        Check if text contains an exact 'Item X' pattern.
        
        Args:
            text: Text to check
            item_no: Item number to look for
            
        Returns:
            True if text contains 'Item X' pattern
        """
        import re
        
        # Clean text
        text_clean = text.strip()
        
        # For Item 0, check for intro/cover patterns
        if item_no == 0:
            intro_patterns = [
                r'^FRANCHISE\s+DISCLOSURE\s+DOCUMENT',
                r'^FDD',
                r'^TABLE\s+OF\s+CONTENTS',
                r'^INTRODUCTION',
                r'^COVER\s+PAGE'
            ]
            for pattern in intro_patterns:
                if re.search(pattern, text_clean, re.IGNORECASE):
                    return True
            return False
        
        # For Items 1-23, look for exact "Item X" pattern
        if 1 <= item_no <= 23:
            # Match patterns like "Item 5", "ITEM 5:", "Item 5.", "Item 5 -"
            patterns = [
                rf'^Item\s+{item_no}\b',
                rf'^ITEM\s+{item_no}\b',
                rf'^Item\s+{item_no}[:\.\-\s]',
                rf'^ITEM\s+{item_no}[:\.\-\s]'
            ]
            for pattern in patterns:
                if re.search(pattern, text_clean, re.IGNORECASE):
                    return True
        
        # For Item 24 (appendix/exhibits)
        if item_no == 24:
            appendix_patterns = [
                r'^APPENDIX',
                r'^EXHIBIT',
                r'^ATTACHMENT'
            ]
            for pattern in appendix_patterns:
                if re.search(pattern, text_clean, re.IGNORECASE):
                    return True
                    
        return False
        
    def _get_max_page_for_item(
        self, 
        item_no: int, 
        by_item: Dict[int, List[FDDSectionCandidate]],
        total_pages: Optional[int]
    ) -> int:
        """
        Get the maximum page number for an item (next section's start page).
        
        Args:
            item_no: Current item number
            by_item: Candidates grouped by item number
            total_pages: Total pages in document
            
        Returns:
            Maximum page number this item can occupy
        """
        # For now, just use document end - we'll refine this after initial pass
        return total_pages or 9999
        
    def _find_sequential_section(
        self,
        item_no: int,
        by_item: Dict[int, List[FDDSectionCandidate]],
        min_page: int,
        total_pages: Optional[int]
    ) -> FDDSectionCandidate:
        """
        Find the best candidate using phased detection approach.
        
        Phase 1: Title elements with "Item X" pattern (highest priority)
        Phase 2: Fuzzy matching (title elements prioritized)
        Phase 3: Pattern matching
        Phase 4: Cosine similarity (lowest priority)
        
        Args:
            item_no: Item number to find (0-24)
            by_item: Candidates grouped by item number
            min_page: Minimum page number this section can start on
            total_pages: Total pages in document
            
        Returns:
            Best valid candidate or interpolated placeholder
        """
        # Determine the maximum page (next section's start or document end)
        max_page = self._get_max_page_for_item(item_no, by_item, total_pages)
        
        if item_no not in by_item:
            logger.debug(f"  No candidates found for Item {item_no}, will interpolate")
            return self._create_interpolated_section(item_no, min_page, total_pages)
        
        all_candidates = by_item[item_no]
        logger.debug(f"  Evaluating {len(all_candidates)} candidates for Item {item_no} "
                    f"(page range: {min_page}-{max_page})")
        
        # Phase 1: Title elements with "Item X" pattern
        phase1_candidates = [
            c for c in all_candidates
            if c.element_type == 'title'
            and self._has_exact_item_pattern(c.text_content, item_no)
            and min_page <= c.page_number < max_page
        ]
        
        if phase1_candidates:
            best = max(phase1_candidates, key=lambda x: (x.confidence, -x.page_number))
            logger.info(f"  PHASE 1 MATCH: Item {item_no} found title with 'Item {item_no}' "
                       f"on page {best.page_number} (conf: {best.confidence:.2f})")
            return best
        
        # Phase 2: Fuzzy matching (title elements get priority)
        phase2_candidates = [
            c for c in all_candidates
            if c.detection_method == 'fuzzy'
            and min_page <= c.page_number < max_page
        ]
        
        if phase2_candidates:
            # Sort by: title elements first, then confidence, then earlier pages
            phase2_candidates.sort(
                key=lambda x: (
                    x.element_type == 'title',  # True sorts before False
                    x.confidence,
                    -x.page_number
                ),
                reverse=True
            )
            best = phase2_candidates[0]
            logger.info(f"  PHASE 2 MATCH: Item {item_no} fuzzy match "
                       f"on page {best.page_number} (conf: {best.confidence:.2f}, "
                       f"type: {best.element_type})")
            return best
        
        # Phase 3: Pattern matching
        phase3_candidates = [
            c for c in all_candidates
            if c.detection_method == 'pattern'
            and min_page <= c.page_number < max_page
        ]
        
        if phase3_candidates:
            best = max(phase3_candidates, key=lambda x: (x.confidence, -x.page_number))
            logger.info(f"  PHASE 3 MATCH: Item {item_no} pattern match "
                       f"on page {best.page_number} (conf: {best.confidence:.2f})")
            return best
        
        # Phase 4: Cosine similarity
        phase4_candidates = [
            c for c in all_candidates
            if c.detection_method == 'cosine'
            and min_page <= c.page_number < max_page
        ]
        
        if phase4_candidates:
            best = max(phase4_candidates, key=lambda x: (x.confidence, -x.page_number))
            logger.info(f"  PHASE 4 MATCH: Item {item_no} cosine match "
                       f"on page {best.page_number} (conf: {best.confidence:.2f})")
            return best
        
        # No valid candidate found in any phase - interpolate
        logger.warning(f"  No valid candidates for Item {item_no} in page range {min_page}-{max_page}")
        return self._create_interpolated_section(item_no, min_page, total_pages)
        
    def _create_interpolated_section(
        self,
        item_no: int,
        min_page: int,
        total_pages: Optional[int]
    ) -> FDDSectionCandidate:
        """Create an interpolated section with reasonable page estimation."""
        total_pages = total_pages or 75
        
        # Use more reasonable interpolation - don't let sections get too spread out
        # Estimate where this section should be based on document proportion
        section_proportion = item_no / 24  # 0 to 1
        estimated_page = max(min_page, int(1 + (total_pages - 1) * section_proportion))
        
        # Ensure we don't exceed reasonable bounds
        interpolated_page = min(estimated_page, total_pages - (24 - item_no))
        interpolated_page = max(interpolated_page, min_page)
        
        # Final bounds check
        if interpolated_page > total_pages:
            interpolated_page = min(total_pages, min_page)
            
        logger.info(f"Interpolating Item {item_no} at page {interpolated_page} (min_page: {min_page}, estimated: {estimated_page})")
        
        return FDDSectionCandidate(
            item_no=item_no,
            item_name=self.STANDARD_FDD_SECTIONS[item_no],
            page_idx=interpolated_page - 1,
            page_number=interpolated_page,
            confidence=0.3,  # Low confidence for interpolated
            text_content=f"Interpolated Item {item_no}",
            bbox=[0, 0, 0, 0],
            detection_method='interpolated',
            element_type='placeholder'
        )
        
    def _create_fallback_sections(self, total_pages: int) -> List[FDDSectionCandidate]:
        """Create evenly distributed fallback sections when no candidates found."""
        sections = []
        pages_per_section = max(1, total_pages // 25)
        
        for item_no in range(25):
            start_page = max(1, (item_no * pages_per_section) + 1)
            
            section = FDDSectionCandidate(
                item_no=item_no,
                item_name=self.STANDARD_FDD_SECTIONS[item_no],
                page_idx=start_page - 1,
                page_number=start_page,
                confidence=0.1,  # Very low confidence for fallback
                text_content=f"Fallback Item {item_no}",
                bbox=[0, 0, 0, 0],
                detection_method='fallback',
                element_type='placeholder'
            )
            sections.append(section)
            
        return sections
        
        
    def _create_section_boundaries(
        self, 
        candidates: List[FDDSectionCandidate],
        total_pages: Optional[int] = None
    ) -> List[SectionBoundary]:
        """
        Convert candidates to SectionBoundary objects with proper overlap calculation.
        
        Overlap Implementation:
        - End page = next section's start page (NOT start page - 1)
        - This creates 1-page overlap as requested by user
        - Last section extends to document end
        """
        boundaries = []
        
        for i, candidate in enumerate(candidates):
            # Calculate end page with overlap
            if i < len(candidates) - 1:
                # End page = next section's start page (creates overlap)
                end_page = candidates[i + 1].page_number
                # Ensure end page is at least the start page
                end_page = max(candidate.page_number, end_page)
            else:
                # Last section extends to document end
                end_page = total_pages or 75
                
            boundary = SectionBoundary(
                item_no=candidate.item_no,
                item_name=candidate.item_name,
                start_page=candidate.page_number,
                end_page=end_page,
                confidence=min(1.0, float(candidate.confidence))  # Ensure confidence <= 1.0
            )
            boundaries.append(boundary)
            
        # Final validation of boundaries
        self._validate_boundaries(boundaries)
            
        return boundaries
        
    def _validate_boundaries(self, boundaries: List[SectionBoundary]) -> None:
        """Validate that boundaries maintain sequential ordering and proper overlap."""
        for i in range(len(boundaries)):
            boundary = boundaries[i]
            
            # Basic validation
            if boundary.start_page > boundary.end_page:
                logger.error(
                    f"Invalid boundary for Item {boundary.item_no}: "
                    f"start_page ({boundary.start_page}) > end_page ({boundary.end_page})"
                )
                
            # Sequential validation
            if i > 0:
                prev_boundary = boundaries[i-1]
                if boundary.start_page < prev_boundary.start_page:
                    logger.error(
                        f"Sequential ordering violation: Item {boundary.item_no} "
                        f"starts on page {boundary.start_page}, before Item {prev_boundary.item_no} "
                        f"which starts on page {prev_boundary.start_page}"
                    )
                    
            # Overlap validation
            if i < len(boundaries) - 1:
                next_boundary = boundaries[i+1]
                if boundary.end_page != next_boundary.start_page:
                    logger.warning(
                        f"Missing overlap: Item {boundary.item_no} ends on page {boundary.end_page}, "
                        f"Item {next_boundary.item_no} starts on page {next_boundary.start_page}"
                    )


def main():
    """Example usage and testing"""
    # Example usage with the Valvoline sample data - using relaxed thresholds for less strict detection
    detector = EnhancedFDDSectionDetector(confidence_threshold=0.5, min_fuzzy_score=75)
    
    sample_json_path = (
        "examples/2025_VALVOLINE INSTANT OIL CHANGE FRANCHISING, INC_32722-202412-04.pdf-"
        "42b85dc3-4422-4724-abf7-344b6d910da3/layout.json"
    )
    
    if Path(sample_json_path).exists():
        sections = detector.detect_sections_from_mineru_json(sample_json_path, total_pages=75)
        
        print(f"\nDetected {len(sections)} FDD sections:")
        print("-" * 80)
        for section in sections:
            print(
                f"Item {section.item_no:2d}: {section.item_name[:50]:<50} "
                f"Pages {section.start_page:3d}-{section.end_page:3d} "
                f"(conf: {section.confidence:.2f})"
            )
    else:
        print(f"Sample file not found: {sample_json_path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s | %(levelname)s | %(name)s - %(message)s')
    main()