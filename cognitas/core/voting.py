import logging
from typing import Dict, Optional, Union

logger = logging.getLogger("cognitas.voting")

class VoteTarget:
    """Constants for special voting targets to avoid magic strings."""
    NO_LYNCH = "NO_LYNCH"

class VotingManager:
    """
    Pure mathematical engine for handling votes.
    Decoupled from Discord, Players, and GameState to ensure absolute testability.
    """
    def __init__(self):
        # Maps voter_id (int) to target_id (int) or NO_LYNCH (str)
        self.votes: Dict[int, Union[int, str]] = {}
        # Maps voter_id (int) to their vote weight (int). Default is usually 1.
        self.weights: Dict[int, int] = {}
        self.end_day_votes: set[int] = set()

    def cast_vote(self, voter_id: int, target: Union[int, str], weight: int = 1) -> None:
        """Records or updates a player's vote with a specific weight."""
        self.votes[voter_id] = target
        self.weights[voter_id] = weight
        logger.debug(f"Voter {voter_id} cast vote for {target} (Weight: {weight}).")

    def unvote(self, voter_id: int) -> None:
        """Removes a player's vote if it exists."""
        if voter_id in self.votes:
            del self.votes[voter_id]
            del self.weights[voter_id]
            logger.debug(f"Voter {voter_id} revoked their vote.")

    def cast_end_day(self, voter_id: int) -> None:
        """Registers a vote to end the day early."""
        self.end_day_votes.add(voter_id)
        logger.debug(f"Voter {voter_id} voted to end the day early.")

    def check_end_day_majority(self, alive_count: int) -> bool:
        """
        Calculates if 2/3 of alive players want to end the day.
        Formula uses integer math to achieve ceiling without importing math module.
        """
        if alive_count <= 0:
            return False
        threshold = (alive_count * 2 + 2) // 3
        return len(self.end_day_votes) >= threshold

    def clear_all_votes(self) -> None:
        """Wipes the voting slate clean. Usually called at phase transition."""
        self.votes.clear()
        self.weights.clear()
        self.end_day_votes.clear()
        logger.info("All votes have been cleared.")

    def get_tally(self) -> Dict[Union[int, str], int]:
        """
        Calculates the current total of votes for each target.
        Returns a dictionary mapping target -> total vote weight.
        """
        tally: Dict[Union[int, str], int] = {}
        for voter_id, target in self.votes.items():
            weight = self.weights.get(voter_id, 1)
            tally[target] = tally.get(target, 0) + weight
        return tally

    def check_majority(self, alive_count: int) -> Optional[Union[int, str]]:
        """
        Determines if any target has reached absolute majority.
        Majority is strictly defined as floor(alive_count / 2) + 1.
        Returns the target if majority is reached, otherwise None.
        """
        if alive_count <= 0:
            return None

        # Absolute majority formula
        threshold = (alive_count // 2) + 1
        tally = self.get_tally()

        for target, total_weight in tally.items():
            if total_weight >= threshold:
                logger.info(f"Majority reached for target {target} with {total_weight} votes.")
                return target
                
        return None