from typing import Dict, Any, Optional, List

class Role:
    """
    Represents a player's role, including their alignment (faction).
    """
    def __init__(self, name: str, alignment: str, flags: Dict[str, Any] = None):
        self.name = name
        self.alignment = alignment
        self.abilities: List['Ability'] = []
        self.flags: Dict[str, Any] = flags if flags is not None else {}

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the role for JSON storage."""
        return {
            "name": self.name,
            "alignment": self.alignment,
            "flags": self.flags # Save flags
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Role':
        """Rebuilds a Role instance from a dictionary."""
            role = cls(
            name=data.get("name", "Unknown"),
            alignment=data.get("alignment", "Unknown"),
            flags=data.get("flags", {})
        )
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
        self.statuses: List['Condition'] = [] # We'll upgrade this to actual Status objects later
        self.private_channel_id: Optional[int] = None

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
            "statuses": []
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Player':
        """Rebuilds a Player instance, cascading to rebuild their Role if present."""
        player = cls(user_id=data["user_id"])
        
        if data.get("role"):
            player.role = Role.from_dict(data["role"])
            
        player.is_alive = data.get("is_alive", True)
        player.private_channel_id = data.get("private_channel_id")
        return player