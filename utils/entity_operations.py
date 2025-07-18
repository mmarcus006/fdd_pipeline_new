"""
Entity Operations for FDD Pipeline

Handles franchise entity deduplication, similarity matching, and resolution.
Uses sentence transformers for name embeddings and cosine similarity for matching.
"""

import re
from typing import List, Dict, Optional, Tuple
import numpy as np
from sentence_transformers import SentenceTransformer
from supabase import Client
import logging

from utils.database import get_supabase_client, DatabaseManager
from config import settings

logger = logging.getLogger(__name__)


class EntityResolver:
    """
    Handles entity resolution for franchises using semantic similarity.

    Uses MiniLM-L6-v2 model for generating 384-dimensional embeddings
    that match the database schema.
    """

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        """
        Initialize the entity resolver with a sentence transformer model.

        Args:
            model_name: Name of the sentence transformer model to use
        """
        self.model = SentenceTransformer(model_name)
        self.db = DatabaseManager()
        self.supabase = get_supabase_client()

    def normalize_franchise_name(self, name: str) -> str:
        """
        Normalize a franchise name for better matching.

        Args:
            name: Raw franchise name

        Returns:
            Normalized name
        """
        # Convert to lowercase
        normalized = name.lower()

        # Remove common suffixes
        suffixes_to_remove = [
            ", inc.",
            ", inc",
            " inc.",
            " inc",
            ", llc",
            " llc",
            ", ltd.",
            ", ltd",
            " ltd.",
            " ltd",
            ", corp.",
            ", corp",
            " corp.",
            " corp",
            ", co.",
            ", co",
            " co.",
            " co",
            ", franchise",
            " franchise",
            ", franchising",
            " franchising",
        ]

        for suffix in suffixes_to_remove:
            if normalized.endswith(suffix):
                normalized = normalized[: -len(suffix)]
                break

        # Remove extra whitespace
        normalized = re.sub(r"\s+", " ", normalized).strip()

        # Remove special characters but keep spaces
        normalized = re.sub(r"[^\w\s-]", "", normalized)

        return normalized

    def generate_embedding(self, text: str) -> np.ndarray:
        """
        Generate a sentence embedding for the given text.

        Args:
            text: Text to embed

        Returns:
            384-dimensional embedding vector
        """
        # Generate embedding
        embedding = self.model.encode(text, convert_to_numpy=True)

        # Ensure it's 384 dimensions (MiniLM-L6-v2 default)
        assert (
            embedding.shape[0] == 384
        ), f"Expected 384 dimensions, got {embedding.shape[0]}"

        return embedding

    def find_similar_franchises(
        self, franchise_name: str, threshold: float = 0.85, limit: int = 10
    ) -> List[Dict]:
        """
        Find franchises similar to the given name using vector similarity.

        Args:
            franchise_name: Name to search for
            threshold: Minimum similarity score (0-1)
            limit: Maximum number of results

        Returns:
            List of similar franchises with scores
        """
        # Normalize and embed the search name
        normalized_name = self.normalize_franchise_name(franchise_name)
        embedding = self.generate_embedding(normalized_name)

        # Convert to list for Supabase
        embedding_list = embedding.tolist()

        try:
            # Use Supabase vector similarity search
            # Note: This requires pgvector extension and proper index
            response = self.supabase.rpc(
                "match_franchises",
                {
                    "query_embedding": embedding_list,
                    "match_threshold": threshold,
                    "match_count": limit,
                },
            ).execute()

            return response.data

        except Exception as e:
            logger.warning(f"Vector search failed, falling back to text search: {e}")

            # Fallback to text-based search
            return self._text_similarity_search(franchise_name, limit)

    def _text_similarity_search(self, franchise_name: str, limit: int) -> List[Dict]:
        """
        Fallback text-based similarity search using normalized names.

        Args:
            franchise_name: Name to search for
            limit: Maximum number of results

        Returns:
            List of similar franchises
        """
        normalized_search = self.normalize_franchise_name(franchise_name)

        # Get all franchises
        franchises = self.db.read("franchisors", limit=1000)

        results = []
        for franchise in franchises:
            normalized_candidate = self.normalize_franchise_name(
                franchise.get("canonical_name", "")
            )

            # Simple fuzzy matching based on common tokens
            search_tokens = set(normalized_search.split())
            candidate_tokens = set(normalized_candidate.split())

            if not search_tokens or not candidate_tokens:
                continue

            # Calculate Jaccard similarity
            intersection = len(search_tokens & candidate_tokens)
            union = len(search_tokens | candidate_tokens)
            similarity = intersection / union if union > 0 else 0

            if similarity >= 0.5:  # Lower threshold for text matching
                results.append(
                    {
                        "id": franchise["id"],
                        "canonical_name": franchise["canonical_name"],
                        "similarity": similarity,
                    }
                )

        # Sort by similarity and limit results
        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:limit]

    def resolve_franchise(
        self,
        franchise_name: str,
        additional_names: List[str] = None,
        auto_create: bool = True,
    ) -> Optional[Dict]:
        """
        Resolve a franchise name to an existing entity or create a new one.

        Args:
            franchise_name: Primary franchise name
            additional_names: List of DBA/alternate names
            auto_create: Whether to create if not found

        Returns:
            Franchise record or None
        """
        # Check for exact match first
        exact_match = self.db.read(
            "franchisors", filters={"canonical_name": franchise_name}
        )

        if exact_match:
            return exact_match[0]

        # Check for similar franchises
        similar = self.find_similar_franchises(franchise_name, threshold=0.9)

        if similar:
            # If very high similarity, assume it's the same franchise
            best_match = similar[0]
            if best_match.get("similarity", 0) >= 0.95:
                logger.info(
                    f"Found high-similarity match: '{franchise_name}' -> "
                    f"'{best_match['canonical_name']}' (score: {best_match['similarity']})"
                )

                # Update DBA names if needed
                if additional_names:
                    self._update_dba_names(best_match["id"], additional_names)

                return self.db.read("franchisors", id=best_match["id"])[0]

        # No good match found
        if auto_create:
            logger.info(f"Creating new franchise entity: '{franchise_name}'")
            return self.create_franchise(franchise_name, additional_names)

        return None

    def create_franchise(
        self,
        canonical_name: str,
        dba_names: List[str] = None,
        parent_company: str = None,
        website: str = None,
    ) -> Dict:
        """
        Create a new franchise entity with embedding.

        Args:
            canonical_name: Primary franchise name
            dba_names: List of alternate names
            parent_company: Parent company name
            website: Franchise website

        Returns:
            Created franchise record
        """
        # Generate embedding for the canonical name
        normalized_name = self.normalize_franchise_name(canonical_name)
        embedding = self.generate_embedding(normalized_name)

        # Prepare franchise data
        franchise_data = {
            "canonical_name": canonical_name,
            "name_embedding": embedding.tolist(),
            "dba_names": dba_names or [],
            "parent_company": parent_company,
            "website": website,
        }

        # Create the franchise
        return self.db.create("franchisors", franchise_data)

    def _update_dba_names(self, franchise_id: str, new_names: List[str]):
        """
        Update DBA names for a franchise, merging with existing ones.

        Args:
            franchise_id: Franchise ID
            new_names: New DBA names to add
        """
        try:
            # Get current franchise
            franchise = self.db.read("franchisors", id=franchise_id)[0]

            # Merge DBA names
            existing_dbas = set(franchise.get("dba_names", []))
            updated_dbas = list(existing_dbas | set(new_names))

            # Update if changed
            if len(updated_dbas) > len(existing_dbas):
                self.db.update("franchisors", franchise_id, {"dba_names": updated_dbas})
                logger.info(f"Updated DBA names for franchise {franchise_id}")

        except Exception as e:
            logger.error(f"Failed to update DBA names: {e}")

    def deduplicate_franchises(self, batch_size: int = 100) -> Dict[str, int]:
        """
        Find and merge duplicate franchises in the database.

        Args:
            batch_size: Number of franchises to process at once

        Returns:
            Statistics about deduplication
        """
        stats = {"processed": 0, "duplicates_found": 0, "merged": 0, "errors": 0}

        # Get all franchises without embeddings first
        franchises_without_embeddings = (
            self.db.query_builder("franchisors").is_null("name_embedding").execute()
        )

        # Generate embeddings for those that don't have them
        for franchise in franchises_without_embeddings.data:
            try:
                embedding = self.generate_embedding(
                    self.normalize_franchise_name(franchise["canonical_name"])
                )

                self.db.update(
                    "franchisors",
                    franchise["id"],
                    {"name_embedding": embedding.tolist()},
                )

            except Exception as e:
                logger.error(f"Failed to generate embedding for {franchise['id']}: {e}")
                stats["errors"] += 1

        # Now process all franchises for deduplication
        offset = 0

        while True:
            # Get batch of franchises
            franchises = self.db.read("franchisors", limit=batch_size, offset=offset)

            if not franchises:
                break

            for franchise in franchises:
                stats["processed"] += 1

                # Find similar franchises (excluding self)
                similar = self.find_similar_franchises(
                    franchise["canonical_name"], threshold=0.95, limit=5
                )

                # Filter out self and process duplicates
                duplicates = [
                    s
                    for s in similar
                    if s["id"] != franchise["id"] and s.get("similarity", 0) >= 0.95
                ]

                if duplicates:
                    stats["duplicates_found"] += len(duplicates)

                    # Merge duplicates into this franchise
                    for dup in duplicates:
                        try:
                            self._merge_franchises(franchise["id"], dup["id"])
                            stats["merged"] += 1
                        except Exception as e:
                            logger.error(f"Failed to merge franchises: {e}")
                            stats["errors"] += 1

            offset += batch_size

        logger.info(f"Deduplication complete: {stats}")
        return stats

    def _merge_franchises(self, primary_id: str, duplicate_id: str):
        """
        Merge a duplicate franchise into the primary one.

        Args:
            primary_id: ID of the franchise to keep
            duplicate_id: ID of the franchise to merge and remove
        """
        # Update all FDDs to point to the primary franchise
        self.db.query_builder("fdds").update({"franchise_id": primary_id}).eq(
            "franchise_id", duplicate_id
        ).execute()

        # Get duplicate franchise data
        duplicate = self.db.read("franchisors", id=duplicate_id)[0]
        primary = self.db.read("franchisors", id=primary_id)[0]

        # Merge DBA names
        merged_dbas = list(
            set(
                primary.get("dba_names", [])
                + duplicate.get("dba_names", [])
                + [duplicate["canonical_name"]]  # Add the duplicate's name as a DBA
            )
        )

        # Update primary franchise with merged data
        updates = {"dba_names": merged_dbas}

        # Merge other fields if primary doesn't have them
        if not primary.get("parent_company") and duplicate.get("parent_company"):
            updates["parent_company"] = duplicate["parent_company"]

        if not primary.get("website") and duplicate.get("website"):
            updates["website"] = duplicate["website"]

        self.db.update("franchisors", primary_id, updates)

        # Delete the duplicate
        self.db.delete("franchisors", duplicate_id)

        logger.info(
            f"Merged franchise '{duplicate['canonical_name']}' ({duplicate_id}) "
            f"into '{primary['canonical_name']}' ({primary_id})"
        )


# Convenience functions for common operations
def find_or_create_franchise(
    franchise_name: str, additional_names: List[str] = None
) -> Dict:
    """
    Find an existing franchise or create a new one.

    Args:
        franchise_name: Franchise name to resolve
        additional_names: List of alternate names

    Returns:
        Franchise record
    """
    resolver = EntityResolver()
    return resolver.resolve_franchise(franchise_name, additional_names)


def deduplicate_all_franchises() -> Dict[str, int]:
    """
    Run deduplication on all franchises in the database.

    Returns:
        Deduplication statistics
    """
    resolver = EntityResolver()
    return resolver.deduplicate_franchises()


def generate_franchise_embedding(franchise_name: str) -> List[float]:
    """
    Generate an embedding for a franchise name.

    Args:
        franchise_name: Name to embed

    Returns:
        384-dimensional embedding as list
    """
    resolver = EntityResolver()
    normalized = resolver.normalize_franchise_name(franchise_name)
    embedding = resolver.generate_embedding(normalized)
    return embedding.tolist()
