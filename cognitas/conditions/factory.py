import logging
from typing import Optional, Dict, Any

# Import all your specific condition classes
from cognitas.conditions.builtin import (
    ParalyzedCondition, DrowsinessCondition, ConfusionCondition, 
    JailedCondition, SilencedCondition, DoubleVoteCondition, 
    SanctionedCondition, WoundedCondition, PoisonedCondition
)

logger = logging.getLogger("cognitas.conditions.factory")

# Map the string IDs from the JSON to the actual Python Classes
CONDITION_MAP = {
    "paralyzed": ParalyzedCondition,
    "drowsiness": DrowsinessCondition,
    "confusion": ConfusionCondition,
    "jailed": JailedCondition,
    "silenced": SilencedCondition,
    "double_vote": DoubleVoteCondition,
    "sanctioned": SanctionedCondition,
    "wounded": WoundedCondition,
    "poisoned": PoisonedCondition
}

def load_condition_from_dict(data: Dict[str, Any]) -> Optional['Condition']:
    """Rebuilds a Condition object from a dictionary."""
    cond_id = data.get("id_name")
    
    if cond_id not in CONDITION_MAP:
        logger.warning(f"Unknown condition ID '{cond_id}' found in save file. Skipping.")
        return None
        
    # Instantiate the correct class
    ConditionClass = CONDITION_MAP[cond_id]
    condition_obj = ConditionClass()
    
    # Restore its active state (duration, stacks, who applied it)
    condition_obj.duration = data.get("duration", condition_obj.duration)
    condition_obj.stacks = data.get("stacks", condition_obj.stacks)
    condition_obj.source_id = data.get("source_id")
    
    return condition_obj