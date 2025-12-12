import threading
from typing import Dict, List, Optional
import time

class Player:
    def __init__(self, session_id: str, name: str):
        self.session_id = session_id
        self.name = name
        self.role: Optional[str] = None
        self.has_acted: bool = False
        self.last_action: Optional[str] = None

class GameManager:
    def __init__(self):
        self._lock = threading.Lock()
        self.players: Dict[str, Player] = {} # session_id -> Player
        self.roles_available: List[str] = []
        self.game_started: bool = False
        self.current_turn: int = 0
        self.history: List[str] = [] # Shared log
        self.engine = None # Reference to ScenarioEngine
        self.host_session_id: Optional[str] = None

    def register_player(self, session_id: str, name: str) -> Player:
        with self._lock:
            if session_id not in self.players:
                self.players[session_id] = Player(session_id, name)
                if self.host_session_id is None:
                    self.host_session_id = session_id
            else:
                # Update name if re-registering
                self.players[session_id].name = name
            return self.players[session_id]

    def set_roles(self, roles: List[str]):
        with self._lock:
            self.roles_available = roles

    def assign_role(self, session_id: str, role: str) -> bool:
        with self._lock:
            # Check if role is taken by someone else
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

    def submit_action(self, session_id: str, action_text: str):
        with self._lock:
            if session_id in self.players:
                self.players[session_id].last_action = action_text
                self.players[session_id].has_acted = True

    def all_players_acted(self) -> bool:
        with self._lock:
            if not self.players:
                return False
            return all(p.has_acted for p in self.players.values() if p.role) # Only count players with roles

    def get_turn_actions(self) -> Dict[str, str]:
        """Returns a dict of Role -> Action for the current turn."""
        with self._lock:
            actions = {}
            for p in self.players.values():
                if p.role and p.last_action:
                    actions[p.role] = p.last_action
            return actions

    def advance_turn(self):
        with self._lock:
            self.current_turn += 1
            # Reset actions
            for p in self.players.values():
                p.has_acted = False
                p.last_action = None

    def reset(self):
        with self._lock:
            self.players = {}
            self.roles_available = []
            self.game_started = False
            self.current_turn = 0
            self.history = []
            self.engine = None
            self.host_session_id = None
