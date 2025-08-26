class Expansion:
    name = "base"

    def on_phase_change(self, game_state, new_phase: str):
        """Hook llamado desde phases: new_phase in {'day','night'}."""
        return
