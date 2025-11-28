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
        self.log: List[str] = []
        self.node_start_time = time.time()
        self.history: List[Dict] = [] # stores visited nodes and choices made

    def get_current_node(self) -> Node:
        return self.nodes_map[self.current_node_id]

    def make_choice(self, choice_index: int):
        """
        Processes a choice made by the user (or auto-selection).
        choice_index is 0-based.
        """
        node = self.get_current_node()

        if choice_index >= len(node.choices):
            # Fallback or error, but we should handle this gracefully
            return

        choice = node.choices[choice_index]

        # Log
        self.log.append(f"Node: {node.text[:50]}... -> Choice: {choice.text}")

        # Calculate Score
        impact_score = 0
        for impact in choice.impacts:
            weight = self.scenario.rubric.weights.get(impact.category, 1.0) # Default weight 1.0 if unknown
            impact_score += impact.value * weight

        self.score += impact_score

        # Record history
        self.history.append({
            "node_id": node.id,
            "choice_id": choice.id,
            "choice_text": choice.text,
            "score_delta": impact_score,
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

    def check_timer(self) -> bool:
        """
        Checks if the timer for the current node has expired.
        Returns True if expired and action was taken (auto-choice).
        """
        node = self.get_current_node()
        if node.type == 'terminal':
            return False

        elapsed = time.time() - self.node_start_time
        if elapsed > node.timer:
            # Time expired. Select 3rd choice (index 2)
            # If less than 3 choices, select the last one.
            idx = 2
            if idx >= len(node.choices):
                idx = len(node.choices) - 1

            if idx >= 0:
                self.log.append(f"TIMEOUT on Node {node.id}. Auto-selecting choice {idx+1}.")
                self.make_choice(idx)
                return True
        return False

    def reset(self):
        self.session_id = str(time.time())
        self.current_node_id = self.start_node.id
        self.score = 0.0
        self.log = []
        self.node_start_time = time.time()
        self.history = []
