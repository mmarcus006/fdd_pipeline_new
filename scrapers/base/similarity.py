"""Franchisor similarity calculations for deduplication."""

import re
from typing import List, Dict, Optional
from difflib import SequenceMatcher

from storage.database.manager import get_database_manager
from utils.logging import get_logger


class SimilarityCalculator:
    """Calculates similarity between franchisors for deduplication.
    
    This class helps identify when different spellings or variations
    of franchisor names actually refer to the same entity.
    """
    
    # Common franchisor name suffixes to normalize
    SUFFIXES = [
        r'\b(LLC|L\.L\.C\.)',
        r'\b(Inc|Inc\.|Incorporated)',
        r'\b(Corp|Corp\.|Corporation)',
        r'\b(Ltd|Ltd\.|Limited)',
        r'\b(Co|Co\.|Company)',
        r'\b(LP|L\.P\.|Limited Partnership)',
        r'\b(LLP|L\.L\.P\.|Limited Liability Partnership)',
        r'\b(PC|P\.C\.|Professional Corporation)',
        r'\b(PA|P\.A\.|Professional Association)',
        r'\b(PLLC|P\.L\.L\.C\.)',
        r'\b(Franchising|Franchise|Franchises)',
        r'\b(International|Intl|Int\'l)',
        r'\b(USA|U\.S\.A\.|US|U\.S\.)',
        r'\b(America|American)',
        r'\b(Systems|System)',
        r'\b(Brands|Brand)',
        r'\b(Group|Grp)',
        r'\b(Holdings|Holding)',
        r'\b(Enterprises|Enterprise)',
        r'\b(Services|Service|Svcs)',
    ]
    
    def __init__(self, similarity_threshold: float = 0.85):
        self.similarity_threshold = similarity_threshold
        self.logger = get_logger(__name__)
        self._suffix_pattern = self._compile_suffix_pattern()
    
    def _compile_suffix_pattern(self) -> re.Pattern:
        """Compile regex pattern for suffix removal."""
        pattern = '|'.join(self.SUFFIXES)
        return re.compile(pattern, re.IGNORECASE)
    
    def normalize_name(self, name: str) -> str:
        """Normalize franchisor name for comparison.
        
        Steps:
        1. Remove common legal suffixes
        2. Remove special characters and punctuation
        3. Normalize whitespace
        4. Convert to lowercase
        """
        # Remove common suffixes
        normalized = self._suffix_pattern.sub('', name)
        
        # Remove special characters but keep spaces
        normalized = re.sub(r'[^\w\s-]', ' ', normalized)
        
        # Replace multiple spaces/hyphens with single space
        normalized = re.sub(r'[-\s]+', ' ', normalized)
        
        # Remove leading/trailing whitespace and convert to lowercase
        normalized = normalized.strip().lower()
        
        return normalized
    
    def calculate_similarity(self, name1: str, name2: str) -> float:
        """Calculate similarity score between two names.
        
        Returns a score between 0 and 1, where:
        - 1.0 = exact match
        - 0.0 = completely different
        """
        norm1 = self.normalize_name(name1)
        norm2 = self.normalize_name(name2)
        
        # Exact match after normalization
        if norm1 == norm2:
            return 1.0
        
        # Check if one is substring of the other (common with DBA names)
        if norm1 in norm2 or norm2 in norm1:
            # Give high score for substring matches
            return 0.95
        
        # Use SequenceMatcher for fuzzy matching
        # This handles typos, word order differences, etc.
        ratio = SequenceMatcher(None, norm1, norm2).ratio()
        
        # Check for word overlap (handles reordered words)
        words1 = set(norm1.split())
        words2 = set(norm2.split())
        if words1 and words2:
            overlap = len(words1 & words2) / max(len(words1), len(words2))
            # Take the maximum of sequence matching and word overlap
            ratio = max(ratio, overlap * 0.9)  # Slightly penalize word-only matches
        
        return ratio
    
    def find_similar_franchisors(
        self, 
        name: str, 
        threshold: Optional[float] = None,
        limit: int = 10
    ) -> List[Dict]:
        """Find similar franchisors in database.
        
        Args:
            name: Franchisor name to search for
            threshold: Similarity threshold (default: self.similarity_threshold)
            limit: Maximum number of results to return
            
        Returns:
            List of similar franchisors sorted by score
        """
        if threshold is None:
            threshold = self.similarity_threshold
            
        try:
            db = get_database_manager()
            
            # Get all franchisors (consider adding pagination for large datasets)
            all_franchisors = db.get_all_records("franchisors", limit=10000)
            
            similar = []
            for franchisor in all_franchisors:
                # Calculate similarity for canonical name
                score = self.calculate_similarity(name, franchisor["canonical_name"])
                
                # Also check trade names if available
                if franchisor.get("trade_names"):
                    for trade_name in franchisor["trade_names"]:
                        trade_score = self.calculate_similarity(name, trade_name)
                        score = max(score, trade_score)
                
                if score >= threshold:
                    similar.append({
                        "id": franchisor["id"],
                        "canonical_name": franchisor["canonical_name"],
                        "trade_names": franchisor.get("trade_names", []),
                        "score": round(score, 3),
                        "match_type": "exact" if score == 1.0 else "fuzzy"
                    })
            
            # Sort by score descending, then by name for stability
            similar.sort(key=lambda x: (-x["score"], x["canonical_name"]))
            
            # Limit results
            similar = similar[:limit]
            
            self.logger.info(
                f"Found {len(similar)} similar franchisors for '{name}' "
                f"(threshold: {threshold})"
            )
            
            return similar
            
        except Exception as e:
            self.logger.error(f"Error finding similar franchisors: {e}")
            return []
    
    def merge_recommendation(self, franchisors: List[Dict]) -> Optional[Dict]:
        """Recommend which franchisors might need merging.
        
        Args:
            franchisors: List of franchisor records with scores
            
        Returns:
            Merge recommendation if high confidence match found
        """
        if not franchisors:
            return None
        
        # If top match has very high score and is significantly better than second
        if len(franchisors) >= 1 and franchisors[0]["score"] >= 0.95:
            if len(franchisors) == 1 or franchisors[0]["score"] - franchisors[1]["score"] > 0.1:
                return {
                    "recommended_id": franchisors[0]["id"],
                    "confidence": "high",
                    "reason": f"Very high similarity score: {franchisors[0]['score']}"
                }
        
        # If multiple high scores, recommend manual review
        high_scores = [f for f in franchisors if f["score"] >= 0.9]
        if len(high_scores) > 1:
            return {
                "recommended_id": None,
                "confidence": "low",
                "reason": f"Multiple potential matches found ({len(high_scores)})",
                "candidates": high_scores
            }
        
        return None