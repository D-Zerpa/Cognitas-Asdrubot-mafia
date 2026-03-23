import logging
from typing import TYPE_CHECKING
from .engine import Condition
from core.actions import ActionTag

if TYPE_CHECKING:
    from core.models import Player
    from core.state import GameState

logger = logging.getLogger("cognitas.conditions.builtin")

# ---------------------------------------------------------
# DEBUFFS (Refresh)
# ---------------------------------------------------------

class ParalyzedCondition(Condition):
    id_name = "paralyzed"
    name = "Paralyzed"
    is_negative = True
    stacking_type = "refresh"

    ui_on_apply = "{mention} ¡Has sido Paralizado!"
    ui_on_block = "Estás Paralizado, no puedes usar tus habilidades."
    ui_on_expire = "{mention} Te has recuperado de la parálisis."

    def can_use_ability(self, tag: 'ActionTag') -> bool:
        # Blocks DAY abilities
        return tag != ActionTag.DAY_ACT

class DrowsinessCondition(Condition):
    id_name = "drowsiness"
    name = "Drowsiness"
    is_negative = True
    stacking_type = "refresh"

    ui_on_apply = "{mention} ¡Has sido afectado por Somnolencia!"
    ui_on_block = "Estás Somnoliento, no puedes usar tus habilidades."
    ui_on_expire = "{mention} Te has recuperado de la somnolencia."

    def can_use_ability(self, tag: 'ActionTag') -> bool:
        # Blocks NIGHT abilities
        return tag != ActionTag.NIGHT_ACT

class ConfusionCondition(Condition):
    id_name = "confusion"
    name = "Confusion"
    is_negative = True
    stacking_type = "refresh"

    ui_on_apply = "{mention} ¡Has sido Confundido!"
    ui_on_try_act = "Estás Confundido, intentas aferrarte a la realidad..."
    ui_on_heads = "¡Genial, lograste usar tu habilidad con éxito!"
    ui_on_tails = "¡Oh no! Perdiste el control, tu habilidad fue redirigida a {new_target}."
    ui_on_expire = "{mention} Te has recuperado de la confusión."

    def get_redirection(self, original_target: Optional[int], valid_targets: List[int]) -> Optional[int]:
        """Tosses a coin. Tails = random redirect. Heads = no redirect."""
        if not valid_targets:
            return None
            
        coin_toss = random.choice(["heads", "tails"])
        
        if coin_toss == "tails":
            # Filter out the original target so it actually redirects to someone else
            possible_new_targets = [t for t in valid_targets if t != original_target]
            if possible_new_targets:
                return random.choice(possible_new_targets)
            return random.choice(valid_targets) # Fallback if only 1 valid target exists
            
        return None

class JailedCondition(Condition):
    id_name = "jailed"
    name = "Jailed"
    is_negative = True
    stacking_type = "refresh"

    ui_on_apply = "{mention} ¡Has sido Encarcelado!"
    ui_on_apply_public = "¡{mention} ha sido Encarcelado/a! No puede hablar ni usar habilidades hasta ser liberado/a."
    ui_on_block = "Estás Encarcelado, no puedes usar tus habilidades."
    ui_on_expire = "{mention} ¡Eres libre de nuevo!"
    ui_on_expire_public = "¡{mention} es libre, puede hablar y usar habilidades de nuevo. Bienvenid@ de vuelta!"

    def can_use_ability(self, tag: 'ActionTag') -> bool:
        return False

    def is_silenced(self) -> bool:
        return True

class SilencedCondition(Condition):
    id_name = "silenced"
    name = "Silenced"
    is_negative = True
    stacking_type = "refresh"

    ui_on_apply = "{mention} ¡Has sido Silenciado!"
    ui_on_apply_public = "¡{mention} ha sido Silenciado/a! No puede hablar."
    ui_on_expire = "{mention} Puedes hablar de nuevo."
    ui_on_expire_public = "¡{mention} puede hablar de nuevo. Bienvenid@ de vuelta!"

    def is_silenced(self) -> bool:
        return True


# ---------------------------------------------------------
# BUFFS & DEBUFFS (Stacking: Sum)
# ---------------------------------------------------------

class DoubleVoteCondition(Condition):
    id_name = "double_vote"
    name = "Double Vote"
    is_negative = False
    stacking_type = "sum"

    ui_on_apply = "{mention} ¡Has sido bendecido con voto doble!"
    ui_on_expire = "{mention} Tu voto doble ha expirado."

    def get_vote_multiplier(self) -> float:
        # 1 stack = 2x, 2 stacks = 4x, 3 stacks = 8x
        return 2.0 ** self.stacks

class SanctionedCondition(Condition):
    id_name = "sanctioned"
    name = "Sanctioned"
    is_negative = True
    stacking_type = "sum"

    ui_on_apply_1 = "{mention} ¡Estás Sancionado, tu voto vale la mitad!"
    ui_on_apply_public_1 = "¡{mention} ha sido Sancionado/a! Su poder de voto se reduce a la mitad."
    ui_on_apply_2 = "{mention} ¡Tu sanción empeoró, ya no puedes votar!"
    ui_on_apply_public_2 = "¡La sanción de {mention} empeoró! ¡Ahora no puede votar!"
    ui_on_block_vote = "¡{mention}, sinvergüenza, no puedes votar!"
    ui_on_expire = "{mention} Tu sanción fue levantada."
    ui_on_expire_public = "La sanción de {mention} fue levantada."

    def get_vote_multiplier(self) -> float:
        if self.stacks == 1:
            return 0.5
        return 0.0  # 2 or more stacks means no vote

class WoundedCondition(Condition):
    id_name = "wounded"
    name = "Wounded"
    is_negative = True
    stacking_type = "sum"

    ui_on_apply_1 = "{mention} Estás Herido, no puedes votar. Mejor corre a buscar a alguien que te cure."
    ui_on_apply_2 = "{mention} ¡Tu herida empeoró, has muerto!"
    ui_on_block_vote = "¡{mention}, estás demasiado débil para votar!"
    ui_on_expire = "{mention} ¡Estás sano de nuevo!" # Used on cleanse/heal

    def get_vote_multiplier(self) -> float:
        return 0.0

    def on_stack(self, player: 'Player', state: 'GameState') -> None:
        """Triggers immediately if a second wound is applied."""
        if self.stacks >= 2 and player.is_alive:
            logger.info(f"Player {player.user_id} died from stacked Wounds.")
            player.kill()

    def on_expire(self, player: 'Player', state: 'GameState') -> None:
        """If duration expires naturally without being cleansed, the player dies."""
        if player.is_alive:
            logger.info(f"Player {player.user_id} bled out from a Wound.")
            player.kill()

class PoisonedCondition(Condition):
    id_name = "poisoned"
    name = "Poisoned"
    is_negative = True
    stacking_type = "sum"

    ui_on_apply_1 = "{mention} Estás Envenenado. Mejor corre a buscar a alguien que te cure."
    ui_on_apply_2 = "{mention} Moriste por envenenamiento. QEPD."
    ui_on_expire_heal = "{mention} ¡Estás sano de nuevo!"

    def on_stack(self, player: 'Player', state: 'GameState') -> None:
        """Triggers immediately if a second poison is applied."""
        if self.stacks >= 2 and player.is_alive:
            logger.info(f"Player {player.user_id} died from stacked Poison.")
            player.kill()

    def on_expire(self, player: 'Player', state: 'GameState') -> None:
        """If duration expires naturally without being cleansed, the player dies."""
        if player.is_alive:
            logger.info(f"Player {player.user_id} died from Poison expiration.")
            player.kill()