import sqlite3
import yaml
import logging
import re
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class Retriever:
    def __init__(self, config_path: str = "d:/financial/agent3_tax_compliance/config/config.yaml"):
        self.config = self._load_config(config_path)
        self.db_path = self.config.get("rag", {}).get("vector_db", {}).get("path", "d:/financial/agent3_tax_compliance/data/database/vector_store.db")

    def _load_config(self, path: str) -> Dict[str, Any]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {path}: {e}")
            return {}

    def retrieve_by_citation(self, citation: str) -> List[Dict[str, Any]]:
        """
        Retrieves the exact chunk matching the given citation.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Try to find an exact or very close citation match using case-insensitive citation_lower column
        query = "SELECT * FROM document_chunks WHERE citation_lower LIKE ?"
        cursor.execute(query, (f"%{citation.strip().lower()}%",))
        rows = cursor.fetchall()
        
        # If no direct match, split terms to search via FTS5
        if not rows:
            clean_citation = re.sub(r"[^\w\s]", " ", citation).strip()
            words = clean_citation.split()
            if words:
                search_expr = " OR ".join([f'"{w}"' for w in words])
                fts_query = "SELECT chunk_id, citation, content FROM fts_chunks WHERE fts_chunks MATCH ? LIMIT 1"
                try:
                    cursor.execute(fts_query, (search_expr,))
                    rows = cursor.fetchall()
                except sqlite3.OperationalError:
                    pass

        results = []
        for row in rows:
            results.append({
                "citation": row["citation"],
                "content": row["content"]
            })
        
        conn.close()
        return results

    def retrieve_by_query(self, query_str: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Retrieves top relevant chunks using SQLite FTS5 BM25 search.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Sanitize query for FTS5 (remove special characters that might break MATCH)
        sanitized_query = re.sub(r"[^\w\s]", " ", query_str).strip()
        words = sanitized_query.split()
        if not words:
            conn.close()
            return []
            
        search_expr = " OR ".join([f'"{w}"' for w in words])

        results = []
        try:
            cursor.execute("""
                SELECT chunk_id, citation, content, rank 
                FROM fts_chunks 
                WHERE fts_chunks MATCH ? 
                ORDER BY rank 
                LIMIT ?
            """, (search_expr, limit))
            rows = cursor.fetchall()
            
            for row in rows:
                results.append({
                    "citation": row["citation"],
                    "content": row["content"],
                    "score": -float(row["rank"])  # In FTS5, lower rank is better (BM25 penalty)
                })
        except sqlite3.OperationalError as e:
            logger.warning(f"FTS5 query failed: {e}. Falling back to LIKE search.")
            like_pattern = f"%{words[0]}%"
            cursor.execute("""
                SELECT citation, content 
                FROM document_chunks 
                WHERE content LIKE ? OR citation LIKE ? 
                LIMIT ?
            """, (like_pattern, like_pattern, limit))
            rows = cursor.fetchall()
            for row in rows:
                results.append({
                    "citation": row["citation"],
                    "content": row["content"],
                    "score": 0.5
                })

        conn.close()
        return results
