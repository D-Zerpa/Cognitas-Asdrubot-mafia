import json
import logging
import os
from typing import Dict

from core.models import Role
from core.actions import Ability, ActionTag, TargetType, ResolutionTime

logger = logging.getLogger("cognitas.data.loader")

class RoleLoader:
    """
    Handles parsing JSON data files and converting them into Engine objects.
    """
    def __init__(self, data_dir: str = "data"):
        # Resolves the path relative to where the bot is executed
        self.data_dir = data_dir

    def load_roles(self, filename: str) -> Dict[str, Role]:
        filepath = os.path.join(self.data_dir, filename)
        if not os.path.exists(filepath):
            logger.error(f"Data file not found: {filepath}")
            return {}

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"JSON syntax error in {filename}: {e}")
            return {}

        roles_dict: Dict[str, Role] = {}
        raw_roles = data.get("roles", {})

        for role_key, role_data in raw_roles.items():
            # 1. Instantiate Role with passive flags
            flags = role_data.get("flags", {})
            role = Role(
                name=role_data.get("name", "Unknown"),
                alignment=role_data.get("alignment", "Unknown"),
                flags=flags
            )

            # 2. Parse and instantiate Abilities
            for ab_data in role_data.get("abilities", []):
                
                # Safely map string values to Engine Enums
                tag_str = ab_data.get("tag", "night_act").upper()
                tag = ActionTag[tag_str] if tag_str in ActionTag.__members__ else ActionTag.NIGHT_ACT
                
                tt_str = ab_data.get("target_type", "single").upper()
                target_type = TargetType[tt_str] if tt_str in TargetType.__members__ else TargetType.SINGLE
                
                res_str = ab_data.get("resolution", "queued").upper()
                resolution = ResolutionTime[res_str] if res_str in ResolutionTime.__members__ else ResolutionTime.QUEUED

                ability = Ability(
                    identifier=ab_data.get("identifier", "unknown"),
                    name=ab_data.get("name", "Unknown Ability"),
                    tag=tag,
                    priority=ab_data.get("priority", 50),
                    accuracy=ab_data.get("accuracy", 100),
                    target_type=target_type,
                    resolution=resolution
                )
                role.abilities.append(ability)

            roles_dict[role_key] = role

        logger.info(f"Successfully loaded {len(roles_dict)} roles from {filename}.")
        return roles_dict