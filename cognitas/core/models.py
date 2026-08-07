from typing import Dict, Any, Optional, List

class Role:
    """
    Represents a player's role, including their alignment (faction).
    """
    def __init__(self, name: str, alignment: str, flags: Dict[str, Any] = None):
        self.name = name
        self.alignment = alignment
        self.abilities = []
        self.flags: Dict[str, Any] = flags if flags is not None else {}

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the role and its abilities for JSON storage."""
        return {
            "name": self.name,
            "alignment": self.alignment,
            "flags": self.flags,
            "abilities": [
                {
                    "identifier": ab.identifier,
                    "name": ab.name,
                    "tag": ab.tag.value,
                    "priority": ab.priority,
                    "accuracy": ab.accuracy,
                    "target_type": ab.target_type.value,
                    "resolution": ab.resolution.value,
                    "requires_note": ab.requires_note
                } for ab in self.abilities
            ]
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Role':
        """Rebuilds a Role instance and its abilities from a dictionary."""
        role = cls(
            name=data.get("name", "Unknown"),
            alignment=data.get("alignment", "Unknown"),
            flags=data.get("flags", {})
        )
        
        from cognitas.core.actions import Ability, ActionTag, TargetType, ResolutionTime
        
        for ab_data in data.get("abilities", []):
            role.abilities.append(Ability(
                identifier=ab_data.get("identifier", "unknown"),
                name=ab_data.get("name", "Unknown Ability"),
                tag=ActionTag(ab_data.get("tag", "night_act")),
                priority=ab_data.get("priority", 50),
                accuracy=ab_data.get("accuracy", 100),
                target_type=TargetType(ab_data.get("target_type", "single")),
                resolution=ResolutionTime(ab_data.get("resolution", "queued")),
                requires_note=ab_data.get("requires_note", False)
            ))
            
        return role


class Player:
    """
    Represents a participant in the match.
    Encapsulates state and logic to prevent direct dictionary manipulation.
    """
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.role: Optional[Role] = None
        self.is_alive: bool = True
        self.statuses = [] 
        self.private_channel_id: Optional[int] = None
        self.inventory: Dict[str, int] = {}

    def kill(self) -> None:
        """Safely marks the player as dead."""
        self.is_alive = False

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the player and their role for JSON storage."""
        return {
            "user_id": self.user_id,
            "role": self.role.to_dict() if self.role else None,
            "is_alive": self.is_alive,
            "private_channel_id": self.private_channel_id,
            "statuses": [cond.to_dict() for cond in self.statuses],
            "inventory": self.inventory
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Player':
        """Rebuilds a Player instance, cascading to rebuild their Role if present."""
        player = cls(user_id=data["user_id"])
        
        if data.get("role"):
            player.role = Role.from_dict(data["role"])
            
        player.is_alive = data.get("is_alive", True)
        player.private_channel_id = data.get("private_channel_id")
        player.inventory = data.get("inventory", {})
        
        from cognitas.conditions.factory import load_condition_from_dict
        
        for cond_data in data.get("statuses", []):
            rebuilt_condition = load_condition_from_dict(cond_data)
            if rebuilt_condition:
                player.statuses.append(rebuilt_condition)
                
        return player