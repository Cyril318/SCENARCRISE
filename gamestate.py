import threading
import json
import time
from typing import Dict, List, Optional


class Player:
    def __init__(self, session_id: str, name: str):
        self.session_id = session_id
        self.name = name
        self.role: Optional[str] = None
        self.has_acted: bool = False
        self.last_action: Optional[str] = None
        self.last_seen: float = time.time()
        self.connected: bool = True


class GameManager:
    def __init__(self):
        self._lock = threading.Lock()
        self.players: Dict[str, Player] = {}  # session_id -> Player
        self.roles_available: List[str] = []
        self.game_started: bool = False
        self.current_turn: int = 0
        self.history: List[str] = []  # Shared log
        self.engine = None  # Reference to ScenarioEngine
        self.host_session_id: Optional[str] = None

        # Action queue: delayed application (fog of war / latence)
        # Actions submitted at turn N are stored in pending_actions.
        # When processing, we send delayed_actions (from turn N-1) to the AI,
        # then promote pending_actions -> delayed_actions for next turn.
        self.pending_actions: Dict[str, str] = {}   # Role -> Action (current turn, queued)
        self.delayed_actions: Dict[str, str] = {}   # Role -> Action (previous turn, applied now)

    def register_player(self, session_id: str, name: str) -> Player:
        with self._lock:
            # Try to reconnect: find existing player with same name but different session_id
            existing_pid = None
            for pid, p in self.players.items():
                if p.name == name and pid != session_id:
                    existing_pid = pid
                    break

            if existing_pid:
                # Migrate old session to new session_id (browser refreshed)
                old_player = self.players.pop(existing_pid)
                old_player.session_id = session_id
                old_player.last_seen = time.time()
                old_player.connected = True
                self.players[session_id] = old_player
                # Update host reference if needed
                if self.host_session_id == existing_pid:
                    self.host_session_id = session_id
                return old_player

            if session_id not in self.players:
                self.players[session_id] = Player(session_id, name)
                if self.host_session_id is None:
                    self.host_session_id = session_id
            else:
                self.players[session_id].name = name
            # Mark as seen and connected
            self.players[session_id].last_seen = time.time()
            self.players[session_id].connected = True
            return self.players[session_id]

    def heartbeat(self, session_id: str):
        """Update last_seen timestamp for a player."""
        with self._lock:
            if session_id in self.players:
                self.players[session_id].last_seen = time.time()
                self.players[session_id].connected = True

    def cleanup_disconnected(self, timeout_seconds: int = 120):
        """Mark players as disconnected if not seen for timeout_seconds.
        Auto-submit pass action for disconnected players with roles."""
        with self._lock:
            now = time.time()
            for pid, p in self.players.items():
                if p.connected and (now - p.last_seen) > timeout_seconds:
                    p.connected = False
                    if p.role and not p.has_acted:
                        p.last_action = "[PASSE (DECONNECTE)]"
                        p.has_acted = True
                        self.pending_actions[p.role] = p.last_action

    def set_roles(self, roles: List[str]):
        with self._lock:
            self.roles_available = roles

    def assign_role(self, session_id: str, role: str) -> bool:
        with self._lock:
            for pid, p in self.players.items():
                if p.role == role and pid != session_id:
                    return False

            if session_id in self.players:
                self.players[session_id].role = role
                return True
            return False

    def start_game(self, engine):
        with self._lock:
            self.engine = engine
            self.game_started = True
            self.current_turn = 1
            self.history.append("Game Started.")
            self.pending_actions = {}
            self.delayed_actions = {}

    def submit_action(self, session_id: str, action_text: str):
        """Submit a player action. It goes into the pending queue (applied next turn)."""
        with self._lock:
            if session_id in self.players:
                player = self.players[session_id]
                player.last_action = action_text
                player.has_acted = True
                # Queue the action for delayed application
                if player.role:
                    self.pending_actions[player.role] = action_text

    def all_players_acted(self) -> bool:
        with self._lock:
            if not self.players:
                return False
            active_players = [p for p in self.players.values() if p.role and p.connected]
            if not active_players:
                return False
            return all(p.has_acted for p in active_players)

    def get_turn_actions(self) -> Dict[str, str]:
        """Returns the DELAYED actions (from previous turn) that are now applied.
        This simulates deployment latency: actions take 1 turn to take effect."""
        with self._lock:
            return dict(self.delayed_actions)

    def get_pending_actions_summary(self) -> Dict[str, str]:
        """Returns current turn's pending actions (for UI display: 'en cours de deploiement')."""
        with self._lock:
            return dict(self.pending_actions)

    def advance_turn(self):
        """Advance to next turn: promote pending -> delayed, reset player actions."""
        with self._lock:
            # Promote: current pending becomes next turn's delayed
            self.delayed_actions = dict(self.pending_actions)
            self.pending_actions = {}
            self.current_turn += 1
            # Reset player action flags
            for p in self.players.values():
                p.has_acted = False
                p.last_action = None

    def process_turn(self, ai_client, random_events: bool = False) -> Optional[str]:
        """Process the current turn: call AI with delayed actions, parse result, update engine.
        Returns an error message string on failure, None on success."""
        from models import Node, SystemState, Inject
        from utils import clean_json_string

        if not self.engine:
            return "No engine available."

        # Get DELAYED actions (from previous turn — fog of war latency)
        applied_actions = self.get_turn_actions()
        applied_summary = "\n".join(
            [f"- {role}: {act}" for role, act in applied_actions.items()]
        ) if applied_actions else "(Aucune action deployee ce tour — les ordres sont en cours d'acheminement)"

        # Get PENDING actions (just submitted — for AI awareness)
        pending = self.get_pending_actions_summary()
        pending_summary = "\n".join(
            [f"- {role}: {act}" for role, act in pending.items()]
        ) if pending else "(Aucune action en attente)"

        current_node = self.engine.get_current_node()

        # Build injects summary for history context
        injects_summary = []
        for inj in current_node.injects:
            target = ", ".join(inj.target_roles) if inj.target_roles else "PUBLIC"
            injects_summary.append(f"[{inj.source} -> {target}] {inj.content[:100]}")
        current_situation = "\n".join(injects_summary) if injects_summary else "(situation initiale)"

        history_str = json.dumps(self.engine.history[-5:], ensure_ascii=False)

        # Current system state (hidden metrics for AI)
        system_state_json = self.engine.system_state.model_dump_json()

        if not ai_client or not ai_client.client:
            return "AI client not available. Re-enter API key."

        json_str = ai_client.generate_next_node(
            history_str,
            current_situation,
            applied_summary,
            pending_summary=pending_summary,
            system_state_json=system_state_json,
            turn_count=self.current_turn,
            random_events_enabled=random_events
        )

        if not json_str:
            return "AI returned empty response."

        json_str_clean = clean_json_string(json_str)

        try:
            next_node_data = json.loads(json_str_clean)
            if isinstance(next_node_data, list):
                next_node_data = next_node_data[0]

            # Extract and apply system_state if present
            sys_state_data = next_node_data.pop("system_state", None)
            if sys_state_data and isinstance(sys_state_data, dict):
                new_state = SystemState(**sys_state_data)
                self.engine.update_system_state(new_state)
                # Also attach to node for history
                next_node_data["system_state"] = sys_state_data

            next_node = Node(**next_node_data)
            if next_node.id in self.engine.nodes_map:
                next_node.id = f"{next_node.id}_{int(time.time())}"

            if next_node.score_reasoning:
                self.engine.apply_turn_score(
                    self.current_turn,
                    next_node.score_delta,
                    next_node.score_reasoning
                )

            self.engine.add_node(next_node)

            # Log with injects details
            injects_log = []
            for inj in next_node.injects:
                injects_log.append({
                    "source": inj.source,
                    "target_roles": inj.target_roles,
                    "content": inj.content[:150]
                })

            self.engine.history.append({
                "turn": self.current_turn,
                "node_id": current_node.id,
                "applied_actions": applied_actions,
                "pending_actions": pending,
                "injects": injects_log,
                "next_node_id": next_node.id
            })

            self.engine.current_node_id = next_node.id
            self.advance_turn()
            return None  # Success

        except (json.JSONDecodeError, ValueError, KeyError, TypeError) as e:
            return f"Error processing turn: {e}"

    def export_game_report(self) -> Dict:
        """Export the full game state for debriefing/download."""
        if not self.engine:
            return {}

        players_data = {}
        for pid, p in self.players.items():
            if p.role:
                players_data[p.role] = p.name

        return {
            "title": self.engine.scenario.environment.branding_title,
            "subtitle": self.engine.scenario.environment.branding_subtitle,
            "total_turns": self.current_turn,
            "final_score": self.engine.score,
            "final_system_state": self.engine.system_state.model_dump(),
            "players": players_data,
            "score_history": self.engine.score_history,
            "history": self.engine.history,
        }

    def reset(self):
        with self._lock:
            self.players = {}
            self.roles_available = []
            self.game_started = False
            self.current_turn = 0
            self.history = []
            self.engine = None
            self.host_session_id = None
            self.pending_actions = {}
            self.delayed_actions = {}
