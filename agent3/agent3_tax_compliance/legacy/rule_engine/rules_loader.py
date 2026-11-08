import os
import json
import logging
from datetime import datetime, date
from typing import List, Dict, Any, Union

logger = logging.getLogger(__name__)

class RulesLoader:
    def __init__(self, rules_dir: str):
        self.rules_dir = rules_dir

    def load_rules(self, doc_date: Union[str, date, datetime]) -> List[Dict[str, Any]]:
        """
        Loads all rules from self.rules_dir that are active on doc_date.
        """
        if not os.path.exists(self.rules_dir):
            logger.warning(f"Rules directory does not exist: {self.rules_dir}")
            return []

        parsed_date = self._parse_date(doc_date)
        if not parsed_date:
            logger.error(f"Invalid date format: {doc_date}. Cannot load rules.")
            return []

        active_rules = []
        for filename in os.listdir(self.rules_dir):
            if not filename.endswith(".json"):
                continue
            
            filepath = os.path.join(self.rules_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    rule = json.load(f)
                
                if self._is_rule_active(rule, parsed_date):
                    active_rules.append(rule)
            except Exception as e:
                logger.error(f"Error loading rule file {filename}: {e}")
        
        logger.info(f"Loaded {len(active_rules)} active rules for date {parsed_date}")
        return active_rules

    def _parse_date(self, val: Union[str, date, datetime]) -> Union[date, None]:
        if isinstance(val, datetime):
            return val.date()
        if isinstance(val, date):
            return val
        if isinstance(val, str):
            try:
                # Remove timestamp / timezone info if present (e.g. 2026-07-19T10:06:49+07:00 or 2026-07-19 10:06:49)
                clean_str = val.split("T")[0].split(" ")[0].strip()
                return datetime.strptime(clean_str, "%Y-%m-%d").date()
            except ValueError:
                pass
        return None

    def _is_rule_active(self, rule: Dict[str, Any], doc_date: date) -> bool:
        """
        Checks if doc_date falls within [effective_from, effective_to] (inclusive).
        """
        effective_from_str = rule.get("effective_from")
        effective_to_str = rule.get("effective_to")

        effective_from = self._parse_date(effective_from_str) if effective_from_str else None
        effective_to = self._parse_date(effective_to_str) if effective_to_str else None

        if effective_from and doc_date < effective_from:
            return False
        if effective_to and doc_date > effective_to:
            return False
        
        return True
