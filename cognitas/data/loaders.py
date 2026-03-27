import json
import logging
import os
from typing import Dict, Any

from cognitas.core.models import Role
from cognitas.core.actions import Ability, ActionTag, TargetType, ResolutionTime

logger = logging.getLogger("cognitas.data.loader")

class RoleLoader:
    """
    Handles parsing JSON data files and converting them into Engine objects.
    Now supports both core Roles and global Temporary Abilities.
    """
    def __init__(self):
        self.data_dir = os.path.dirname(os.path.abspath(__file__))

    def _parse_ability(self, ab_data: dict) -> Ability:
        """Helper method to safely parse a dictionary into an Ability object."""
        tag_str = ab_data.get("tag", "night_act").upper()
        tag = ActionTag[tag_str] if tag_str in ActionTag.__members__ else ActionTag.NIGHT_ACT
        
        tt_str = ab_data.get("target_type", "single").upper()
        target_type = TargetType[tt_str] if tt_str in TargetType.__members__ else TargetType.SINGLE
        
        res_str = ab_data.get("resolution", "queued").upper()
        resolution = ResolutionTime[res_str] if res_str in ResolutionTime.__members__ else ResolutionTime.QUEUED

        return Ability(
            identifier=ab_data.get("identifier", "unknown"),
            name=ab_data.get("name", "Unknown Ability"),
            tag=tag,
            priority=ab_data.get("priority", 50),
            accuracy=ab_data.get("accuracy", 100),
            target_type=target_type,
            resolution=resolution
        )

    def load_expansion_data(self, filename: str) -> Dict[str, Any]:
        """
        Loads the JSON file and returns a dictionary containing:
        - "roles": Dict[str, Role]
        - "temp_abilities": Dict[str, Ability]
        """
        filepath = os.path.join(self.data_dir, "json", filename)
        
        if not os.path.exists(filepath):
            logger.error(f"Data file not found: {filepath}")
            return {"roles": {}, "temp_abilities": {}}

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"JSON syntax error in {filename}: {e}")
            return {"roles": {}, "temp_abilities": {}}

        # 1. Parse Roles
        roles_dict: Dict[str, Role] = {}
        raw_roles = data.get("roles", {})

        for role_key, role_data in raw_roles.items():
            flags = role_data.get("flags", {})
            role = Role(
                name=role_data.get("name", "Unknown"),
                alignment=role_data.get("alignment", "Unknown"),
                flags=flags
            )

            for ab_data in role_data.get("abilities", []):
                ability = self._parse_ability(ab_data)
                role.abilities.append(ability)

            roles_dict[role_key] = role

        # 2. Parse Temporary Abilities (Items/Flags)
        temp_abs_dict: Dict[str, Ability] = {}
        raw_temps = data.get("temporary_abilities", {})
        
        for flag_key, ab_data in raw_temps.items():
            ability = self._parse_ability(ab_data)
            temp_abs_dict[flag_key] = ability

        recommended_flags = data.get("recommended_flags", {})

        logger.info(f"Successfully loaded {len(roles_dict)} roles and {len(temp_abs_dict)} temp abilities from {filename}.")
        
        return {
            "roles": roles_dict,
            "temp_abilities": temp_abs_dict,
            "recommended_flags": recommended_flags
        }