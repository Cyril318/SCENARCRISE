import time
from typing import Optional, List, Dict
from models import Scenario, Node, Choice, SystemState, Inject


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
        self.history: List[Dict] = []
        self.score_history: List[Dict] = []

        # Narrative memory: cumulative summary of key facts, entities, and events
        # Updated by AI each turn to maintain story coherence across the whole game
        self.narrative_memory: str = ""

        # Hidden system state (fog of war)
        if self.start_node.system_state:
            self.system_state = self.start_node.system_state
        else:
            self.system_state = SystemState()

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

    def update_system_state(self, new_state: SystemState):
        """Replace the hidden system state with AI-generated update."""
        self.system_state = new_state

    def add_node(self, node: Node):
        """Adds a new node to the scenario map and resets the timer."""
        self.nodes_map[node.id] = node
        self.node_start_time = time.time()
        # Update system state if the node carries one
        if node.system_state:
            self.system_state = node.system_state

    def get_current_node(self) -> Node:
        return self.nodes_map[self.current_node_id]

    def get_injects_summary(self) -> str:
        """Return a text summary of current node injects for logging."""
        node = self.get_current_node()
        lines = []
        for inj in node.injects:
            target = ", ".join(inj.target_roles) if inj.target_roles else "PUBLIC"
            lines.append(f"[{inj.source} -> {target}] {inj.content[:80]}")
        return "\n".join(lines)

    def make_choice(self, choice_index: int):
        """Processes a choice made by the user (single-player legacy)."""
        node = self.get_current_node()

        if choice_index >= len(node.choices):
            return

        choice = node.choices[choice_index]

        duration = time.time() - self.node_start_time
        time_impact = 0.0
        if node.timer > 0:
            diff = node.timer - duration
            time_impact = diff * 0.1

        self.log.append(f"Node: {self.get_injects_summary()[:50]}... -> Choice: {choice.text} (Time: {duration:.1f}s, Impact: {time_impact:.1f})")

        impact_score = 0
        for impact in choice.impacts:
            weight = self.scenario.rubric.weights.get(impact.category, 1.0)
            impact_score += impact.value * weight

        total_delta = impact_score + time_impact
        self.score += total_delta
        self.last_score_delta = total_delta

        self.history.append({
            "node_id": node.id,
            "choice_id": choice.id,
            "choice_text": choice.text,
            "score_delta": total_delta,
            "time_taken": duration,
            "timestamp": time.time()
        })

        if choice.next_node_id and choice.next_node_id in self.nodes_map:
            self.current_node_id = choice.next_node_id
            self.node_start_time = time.time()
        else:
            if node.type != 'terminal':
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
        self.system_state = SystemState()
        self.narrative_memory = ""
