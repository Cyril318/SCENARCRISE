import time
from typing import Optional, List, Dict
from models import Scenario, Node, Choice

class ScenarioEngine:
    def __init__(self, scenario: Scenario):
        self.scenario = scenario
        self.nodes_map = {n.id: n for n in self.scenario.nodes}
        self.start_node = next(n for n in self.scenario.nodes if n.type == 'start')

        # State
        self.session_id = str(time.time())
        self.current_node_id = self.start_node.id
        self.score = 0.0
        self.last_score_delta = 0.0
        self.log: List[str] = []
        self.node_start_time = time.time()
        self.history: List[Dict] = [] # stores visited nodes and choices made
        self.score_history: List[Dict] = [] # stores score evolution

    def apply_turn_score(self, turn: int, delta: float, reasoning: str):
        """Applies score changes for a turn (used in AI multiplayer)."""
        self.score += delta
        self.last_score_delta = delta
        self.score_history.append({
            "turn": turn,
            "score": self.score,
            "delta": delta,
            "reasoning": reasoning
        })

    def add_node(self, node: Node):
        """Adds a new node to the scenario map and resets the timer."""
        self.nodes_map[node.id] = node
        self.node_start_time = time.time()

    def get_current_node(self) -> Node:
        return self.nodes_map[self.current_node_id]

    def make_choice(self, choice_index: int):
        """
        Processes a choice made by the user.
        choice_index is 0-based.
        """
        node = self.get_current_node()

        if choice_index >= len(node.choices):
            # Fallback or error, but we should handle this gracefully
            return

        choice = node.choices[choice_index]

        # Calculate time taken
        duration = time.time() - self.node_start_time
        # Time score: if user is faster than node.timer, bonus? If slower, penalty?
        # Let's implement a simple penalty for taking longer than expected.
        # Score -= (duration - target) * factor if duration > target
        # Or Score += (target - duration) * factor if duration < target?
        # User said "critère de temps doit encore être pris en compte".
        # Let's define a time factor. Say 0.5 points per second difference.
        time_impact = 0.0
        if node.timer > 0:
            diff = node.timer - duration
            # If diff is positive (fast), small bonus. If negative (slow), penalty.
            time_impact = diff * 0.1 # Weight 0.1 per second

        # Log
        self.log.append(f"Node: {node.text[:50]}... -> Choice: {choice.text} (Time: {duration:.1f}s, Impact: {time_impact:.1f})")

        # Calculate Score
        impact_score = 0
        for impact in choice.impacts:
            weight = self.scenario.rubric.weights.get(impact.category, 1.0) # Default weight 1.0 if unknown
            impact_score += impact.value * weight

        # Add time impact to total score
        total_delta = impact_score + time_impact
        self.score += total_delta
        self.last_score_delta = total_delta

        # Record history
        self.history.append({
            "node_id": node.id,
            "choice_id": choice.id,
            "choice_text": choice.text,
            "score_delta": total_delta,
            "time_taken": duration,
            "timestamp": time.time()
        })

        # Move to next node
        if choice.next_node_id and choice.next_node_id in self.nodes_map:
            self.current_node_id = choice.next_node_id
            self.node_start_time = time.time() # Reset timer for new node
        else:
            # End of scenario if no next node
            if node.type != 'terminal':
                # Should not happen if validated, but handle it
                pass
            pass

    def reset(self):
        self.session_id = str(time.time())
        self.current_node_id = self.start_node.id
        self.score = 0.0
        self.last_score_delta = 0.0
        self.log = []
        self.node_start_time = time.time()
        self.history = []
        self.score_history = []
