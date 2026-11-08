import sqlite3
import json
import os
import yaml
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, config_path: str = "d:/financial/agent3_tax_compliance/config/config.yaml"):
        self.config = self._load_config(config_path)
        self.db_path = self.config.get("database", {}).get("path", "d:/financial/agent3_tax_compliance/data/database/tax_compliance.db")
        
        # Ensure database directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
            
        self._init_db()

    def _load_config(self, path: str) -> Dict[str, Any]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Failed to load config from {path}: {e}")
            return {}

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create transactions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                description TEXT NOT NULL,
                description_redacted TEXT,
                amount REAL NOT NULL,
                payment_method TEXT,
                expense_category TEXT,
                beneficiary_type TEXT,
                has_docs INTEGER,
                is_personal_expense INTEGER,
                verdict TEXT,
                rules_triggered TEXT,
                explanation TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Drop old views if exist
        cursor.execute("DROP VIEW IF EXISTS view_internal_audit")
        cursor.execute("DROP VIEW IF EXISTS view_tax_inspector")
        
        # Create View 1: Internal Audit (shows everything, including PII and explanations)
        cursor.execute("""
            CREATE VIEW view_internal_audit AS
            SELECT 
                id,
                date,
                description AS raw_description,
                description_redacted,
                amount,
                payment_method,
                expense_category,
                beneficiary_type,
                has_docs,
                is_personal_expense,
                verdict,
                rules_triggered,
                explanation,
                created_at
            FROM transactions
        """)
        
        # Create View 2: Tax Inspector (hides PII - only shows description_redacted, filters out non-deductible/failed items)
        cursor.execute("""
            CREATE VIEW view_tax_inspector AS
            SELECT 
                id,
                date,
                description_redacted AS description,
                amount,
                payment_method,
                expense_category,
                'Đủ điều kiện khấu trừ' AS status
            FROM transactions
            WHERE verdict = 'PASS' AND is_personal_expense = 0
        """)
        
        conn.commit()
        conn.close()
        logger.info(f"Database initialized and views created at {self.db_path}")

    def insert_transaction(self, tx_data: Dict[str, Any]) -> int:
        """
        Inserts a processed transaction.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO transactions (
                date, description, description_redacted, amount, payment_method, 
                expense_category, beneficiary_type, has_docs, is_personal_expense, 
                verdict, rules_triggered, explanation
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tx_data["date"],
            tx_data["description"],
            tx_data.get("description_redacted", ""),
            tx_data["amount"],
            tx_data.get("payment_method", ""),
            tx_data.get("expense_category", ""),
            tx_data.get("beneficiary_type", ""),
            1 if tx_data.get("has_docs") else 0,
            1 if tx_data.get("is_personal_expense") else 0,
            tx_data.get("verdict", "REVIEW"),
            json.dumps(tx_data.get("rules_triggered", [])),
            tx_data.get("explanation", "")
        ))
        
        tx_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return tx_id

    def get_internal_view(self) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM view_internal_audit")
        rows = cursor.fetchall()
        results = [dict(r) for r in rows]
        conn.close()
        return results

    def get_tax_inspector_view(self) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM view_tax_inspector")
        rows = cursor.fetchall()
        results = [dict(r) for r in rows]
        conn.close()
        return results
