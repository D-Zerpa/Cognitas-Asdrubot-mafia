import logging
from typing import Dict, Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from cognitas.core.state import GameState

logger = logging.getLogger("cognitas.voting")

class VoteTarget:
    """Constants for special voting targets to avoid magic strings."""
    NO_LYNCH = "NO_LYNCH"

class VotingManager:
    """
    Pure mathematical engine for handling votes.
    Now 100% Stateless: reads and writes directly to GameState for persistence.
    """
    def __init__(self):
        pass

    def cast_vote(self, state: 'GameState', voter_id: int, target: Union[int, str], weight: int = 1) -> None:
        """Records or updates a player's vote with a specific weight."""
        state.votes[voter_id] = target
        state.vote_weights[voter_id] = weight
        logger.debug(f"Voter {voter_id} cast vote for {target} (Weight: {weight}).")

    def unvote(self, state: 'GameState', voter_id: int) -> None:
        """Removes a player's vote if it exists."""
        if voter_id in state.votes:
            del state.votes[voter_id]
            if voter_id in state.vote_weights:
                del state.vote_weights[voter_id]
            logger.debug(f"Voter {voter_id} revoked their vote.")

    def cast_end_day(self, state: 'GameState', voter_id: int) -> None:
        """Registers a vote to end the day early."""
        state.end_day_votes.add(voter_id)
        logger.debug(f"Voter {voter_id} voted to end the day early.")

    def check_end_day_majority(self, state: 'GameState', alive_count: int) -> bool:
        """Calculates if 2/3 of alive players want to end the day."""
        if alive_count <= 0:
            return False
        threshold = (alive_count * 2 + 2) // 3
        return len(state.end_day_votes) >= threshold

    def clear_all_votes(self, state: 'GameState') -> None:
        """Wipes the voting slate clean. Usually called at phase transition."""
        state.votes.clear()
        state.vote_weights.clear()
        state.end_day_votes.clear()
        logger.info("All votes have been cleared from the state.")

    def get_tally(self, state: 'GameState') -> Dict[Union[int, str], int]:
        """
        Calculates the current total of votes for each target.
        """
        tally: Dict[Union[int, str], int] = {}
        for voter_id, target in state.votes.items():
            weight = state.vote_weights.get(voter_id, 1)
            tally[target] = tally.get(target, 0) + weight
        return tally

    def check_majority(self, state: 'GameState', alive_count: int, extra_thresholds: Dict[Union[int, str], int] = None) -> Optional[Union[int, str]]:
        """Determines if any target has reached absolute majority."""
        if alive_count <= 0:
            return None

        base_threshold = (alive_count // 2) + 1
        extra_thresholds = extra_thresholds or {}
        
        tally = self.get_tally(state)

        for target, total_weight in tally.items():
            target_threshold = base_threshold + extra_thresholds.get(target, 0)
            if total_weight >= target_threshold:
                logger.info(f"Majority reached for target {target} with {total_weight} votes.")
                return target
                
        return None