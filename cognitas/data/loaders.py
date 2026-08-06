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
        tag_val = ab_data.get("tag")
        tag_str = str(tag_val).upper() if isinstance(tag_val, str) else "NIGHT_ACT"
        tag = ActionTag[tag_str] if tag_str in ActionTag.__members__ else ActionTag.NIGHT_ACT
        
        tt_val = ab_data.get("target_type")
        tt_str = str(tt_val).upper() if isinstance(tt_val, str) else "SINGLE"
        target_type = TargetType[tt_str] if tt_str in TargetType.__members__ else TargetType.SINGLE
        
        res_val = ab_data.get("resolution")
        res_str = str(res_val).upper() if isinstance(res_val, str) else "QUEUED"
        resolution = ResolutionTime[res_str] if res_str in ResolutionTime.__members__ else ResolutionTime.QUEUED

        try:
            priority = int(ab_data.get("priority", 50))
        except (ValueError, TypeError):
            priority = 50

        try:
            accuracy = int(ab_data.get("accuracy", 100))
        except (ValueError, TypeError):
            accuracy = 100

        return Ability(
            identifier=str(ab_data.get("identifier", "unknown")),
            name=str(ab_data.get("name", "Unknown Ability")),
            tag=tag,
            priority=priority,
            accuracy=accuracy,
            target_type=target_type,
            resolution=resolution,
            requires_note=bool(ab_data.get("requires_note", False))
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

        # Ensure the parsed JSON is actually a dictionary at its root
        if not isinstance(data, dict):
            logger.error(f"Invalid JSON structure in {filename}: Expected a dictionary at the root.")
            return {"roles": {}, "temp_abilities": {}}

        # 1. Parse Roles
        roles_dict: Dict[str, Role] = {}
        raw_roles = data.get("roles", {})
        
        # Guard against "roles" being something else like a string or null
        if not isinstance(raw_roles, dict):
            logger.error(f"Invalid 'roles' structure in {filename}: Expected a dictionary.")
            raw_roles = {}

        for role_key, role_data in raw_roles.items():
            if not isinstance(role_data, dict):
                logger.warning(f"Skipping malformed role '{role_key}': Expected a dictionary.")
                continue

            flags = role_data.get("flags", {})
            role = Role(
                name=role_data.get("name", "Unknown"),
                alignment=role_data.get("alignment", "Unknown"),
                flags=flags if isinstance(flags, dict) else {}
            )

            # Safely parse abilities only if it's a list
            raw_abilities = role_data.get("abilities", [])
            if isinstance(raw_abilities, list):
                for ab_data in raw_abilities:
                    if isinstance(ab_data, dict):
                        ability = self._parse_ability(ab_data)
                        role.abilities.append(ability)
                    else:
                        logger.warning(f"Skipping malformed ability in role '{role_key}'.")
            else:
                logger.warning(f"Abilities for role '{role_key}' must be a list. Skipping.")

            roles_dict[role_key] = role

        # 2. Parse Temporary Abilities (Items/Flags)
        temp_abs_dict: Dict[str, Any] = {}
        raw_temps = data.get("temporary_abilities", {})
        
        if not isinstance(raw_temps, dict):
            logger.error(f"Invalid 'temporary_abilities' structure in {filename}: Expected a dictionary.")
            raw_temps = {}
        
        for flag_key, ab_data_or_list in raw_temps.items():
            if isinstance(ab_data_or_list, list):
                # Safely parse only elements that are actually dictionaries
                valid_abs = [self._parse_ability(ab) for ab in ab_data_or_list if isinstance(ab, dict)]
                if valid_abs:
                    temp_abs_dict[flag_key] = valid_abs
                else:
                    logger.warning(f"Skipping malformed temporary ability list for flag '{flag_key}'.")
            elif isinstance(ab_data_or_list, dict):
                # Flag gives only one ability safely
                temp_abs_dict[flag_key] = self._parse_ability(ab_data_or_list)
            else:
                logger.warning(f"Skipping malformed temporary ability for flag '{flag_key}': Expected dict or list.")

        recommended_flags = data.get("recommended_flags", {})

        logger.info(f"Successfully loaded {len(roles_dict)} roles and {len(temp_abs_dict)} temp abilities from {filename}.")
        
        return {
            "roles": roles_dict,
            "temp_abilities": temp_abs_dict,
            "recommended_flags": recommended_flags
        }