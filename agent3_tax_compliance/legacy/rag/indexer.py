import os
import sqlite3
import re
import yaml
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class Indexer:
    def __init__(self, config_path: str = "d:/financial/agent3_tax_compliance/config/config.yaml"):
        self.config = self._load_config(config_path)
        self.corpus_dir = self.config.get("rag", {}).get("corpus_dir", "d:/financial/agent3_tax_compliance/data/corpus")
        self.db_path = self.config.get("rag", {}).get("vector_db", {}).get("path", "d:/financial/agent3_tax_compliance/data/database/vector_store.db")
        
        # Ensure database directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)

    def _load_config(self, path: str) -> Dict[str, Any]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {path}: {e}")
            return {}

    def parse_markdown(self, filepath: str) -> List[Dict[str, Any]]:
        """
        Parses a Vietnamese tax markdown document and splits it into chunks at the Clause level (###).
        """
        if not os.path.exists(filepath):
            logger.error(f"File not found: {filepath}")
            return []

        doc_name = os.path.basename(filepath).replace(".md", "")
        with open(filepath, "r", encoding="utf-8") as f:
            lines = f.readlines()

        chunks = []
        current_doc_title = ""
        current_article = ""
        current_clause = ""
        current_content = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            # Document Title
            if stripped.startswith("# "):
                if current_content and current_clause:
                    chunks.append(self._create_chunk(doc_name, current_doc_title, current_article, current_clause, current_content))
                current_doc_title = stripped.replace("# ", "").strip()
                current_content = []
            
            # Article (##)
            elif stripped.startswith("## "):
                if current_content and (current_clause or current_article):
                    chunks.append(self._create_chunk(doc_name, current_doc_title, current_article, current_clause, current_content))
                current_article = stripped.replace("## ", "").strip()
                current_clause = ""
                current_content = [line]  # Keep the heading in the content for context

            # Clause (###)
            elif stripped.startswith("### "):
                if current_content and (current_clause or current_article):
                    chunks.append(self._create_chunk(doc_name, current_doc_title, current_article, current_clause, current_content))
                current_clause = stripped.replace("### ", "").strip()
                current_content = [line]

            else:
                current_content.append(line)

        # Flush final chunk
        if current_content and (current_clause or current_article):
            chunks.append(self._create_chunk(doc_name, current_doc_title, current_article, current_clause, current_content))

        logger.info(f"Parsed {len(chunks)} chunks from {doc_name}")
        return chunks

    def _create_chunk(self, doc_id: str, doc_title: str, article: str, clause: str, content_lines: List[str]) -> Dict[str, Any]:
        content = "".join(content_lines).strip()
        
        # Build canonical citation: e.g. "Khoản 1 Điều 4 Thông tư 96/2015/TT-BTC"
        citation_parts = []
        if clause:
            # Extract clause prefix if any (e.g. "Khoản 1. Các khoản..." -> "Khoản 1")
            clean_clause = clause.split(".")[0].strip()
            citation_parts.append(clean_clause)
        if article:
            clean_article = article.split(".")[0].strip()
            citation_parts.append(clean_article)
        
        # Add doc title or type
        doc_type_match = re.search(r"(Thông tư \d+/\d+/TT-BTC|Nghị định \d+/\d+/NĐ-CP)", doc_title, re.IGNORECASE)
        if doc_type_match:
            citation_parts.append(doc_type_match.group(1))
        else:
            # Fallback to document ID
            citation_parts.append(doc_id.replace("_", "/"))

        citation = " ".join(citation_parts)

        return {
            "doc_name": doc_id,
            "article": article,
            "clause": clause,
            "citation": citation,
            "content": content
        }

    def build_index(self):
        """
        Parses all markdown files in corpus_dir and builds FTS5 index in SQLite.
        """
        if not os.path.exists(self.corpus_dir):
            logger.error(f"Corpus directory not found: {self.corpus_dir}")
            return

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create standard metadata table
        cursor.execute("DROP TABLE IF EXISTS document_chunks")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_name TEXT,
                article TEXT,
                clause TEXT,
                citation TEXT,
                citation_lower TEXT,
                content TEXT
            )
        """)

        # Create FTS5 virtual table for full-text search
        cursor.execute("DROP TABLE IF EXISTS fts_chunks")
        cursor.execute("""
            CREATE VIRTUAL TABLE fts_chunks USING fts5(
                chunk_id,
                citation,
                content,
                tokenize="unicode61"
            )
        """)

        # Clear existing data
        cursor.execute("DELETE FROM document_chunks")

        # Parse and insert files
        for filename in os.listdir(self.corpus_dir):
            if filename.endswith(".md"):
                filepath = os.path.join(self.corpus_dir, filename)
                chunks = self.parse_markdown(filepath)
                
                for chunk in chunks:
                    cursor.execute("""
                        INSERT INTO document_chunks (doc_name, article, clause, citation, citation_lower, content)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (chunk["doc_name"], chunk["article"], chunk["clause"], chunk["citation"], chunk["citation"].lower(), chunk["content"]))
                    
                    chunk_id = cursor.lastrowid
                    cursor.execute("""
                        INSERT INTO fts_chunks (chunk_id, citation, content)
                        VALUES (?, ?, ?)
                    """, (chunk_id, chunk["citation"], chunk["content"]))

        conn.commit()
        conn.close()
        logger.info(f"Database indexed successfully at {self.db_path}")

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    indexer = Indexer()
    indexer.build_index()
