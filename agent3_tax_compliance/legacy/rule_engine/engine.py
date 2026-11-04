import logging
from typing import Dict, Any, List, Union
from src.rule_engine.rules_loader import RulesLoader

logger = logging.getLogger(__name__)

class RuleEngine:
    def __init__(self, rules_loader: RulesLoader):
        self.rules_loader = rules_loader

    def evaluate(self, transaction: Dict[str, Any], doc_date: str) -> Dict[str, Any]:
        """
        Evaluates a transaction dictionary against all rules active on doc_date.
        Returns a dict indicating the final verdict, list of triggered rules (hits), and metadata.
        """
        active_rules = self.rules_loader.load_rules(doc_date)
        hits = []
        verdicts = []

        for rule in active_rules:
            rule_id = rule.get("rule_id")
            conditions = rule.get("conditions", [])
            
            # Evaluate all conditions in the rule (AND logic by default)
            rule_triggered = True
            for cond in conditions:
                if not self._evaluate_condition(transaction, cond):
                    rule_triggered = False
                    break
            
            if rule_triggered:
                verdict = rule.get("verdict", "REVIEW")
                hits.append({
                    "rule_id": rule_id,
                    "verdict": verdict,
                    "fixable": rule.get("fixable", False),
                    "fix_hint": rule.get("fix_hint", ""),
                    "citation": rule.get("citation", "")
                })
                verdicts.append(verdict)

        # Determine final verdict. Priority: FAIL > REVIEW > PASS
        if "FAIL" in verdicts:
            final_verdict = "FAIL"
        elif "REVIEW" in verdicts:
            final_verdict = "REVIEW"
        else:
            final_verdict = "PASS"

        return {
            "verdict": final_verdict,
            "hits": hits,
            "checked_at": doc_date,
            "rules_evaluated_count": len(active_rules)
        }

    def _evaluate_condition(self, transaction: Dict[str, Any], condition: Dict[str, Any]) -> bool:
        field = condition.get("field")
        operator = condition.get("operator")
        
        # Get target value, either static ('value') or dynamic ('value_field' referencing transaction)
        if "value" in condition:
            target_val = condition.get("value")
        elif "value_field" in condition:
            target_field = condition.get("value_field")
            target_val = transaction.get(target_field)
            if target_val is None:
                logger.warning(f"Target value_field '{target_field}' not found in transaction.")
                return False
        else:
            logger.warning("Condition has neither 'value' nor 'value_field'.")
            return False

        # Get transaction value
        txn_val = transaction.get(field)
        if txn_val is None:
            # If the transaction is missing the field, condition evaluates to False
            return False

        # Execute operators
        try:
            if operator == "==":
                return txn_val == target_val
            elif operator == "!=":
                return txn_val != target_val
            elif operator == ">":
                return float(txn_val) > float(target_val)
            elif operator == ">=":
                return float(txn_val) >= float(target_val)
            elif operator == "<":
                return float(txn_val) < float(target_val)
            elif operator == "<=":
                return float(txn_val) <= float(target_val)
            elif operator == "in":
                if isinstance(target_val, list):
                    return txn_val in target_val
                return str(txn_val) in str(target_val)
            elif operator == "contains":
                return target_val in txn_val
            else:
                logger.error(f"Unsupported operator: {operator}")
                return False
        except (ValueError, TypeError) as e:
            logger.error(f"Error evaluating condition ({field} {operator} {target_val}) with txn value {txn_val}: {e}")
            return False
