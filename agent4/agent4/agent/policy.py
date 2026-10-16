"""Experimental behavior policy; uncertain questions get clarification."""
from dataclasses import dataclass
from .tools import Principal

@dataclass
class AgentConfig:
    max_steps: int = 4
    repair_attempts: int = 2
    verify_attempts: int = 2
    max_duration_s: float = 20.0
    commentary: bool = True

def should_clarify(candidates,hints):
    return not candidates or 'needs_clarification' in hints.cues

def use_think(hints,candidates):
    # No accuracy evidence for enabling thinking in M1.
    return False
