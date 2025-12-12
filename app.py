import streamlit as st
import pandas as pd
import json
import time
import socket
import uuid

from models import Scenario, Node, Environment, ScoringRubric, Choice
from engine import ScenarioEngine
from utils import load_json_scenario, load_csv_data, extract_roles_from_csv
from ai import AIIntegration
from gamestate import GameManager

# Page Config
st.set_page_config(page_title="CrisisSim AI Multiplayer", layout="wide", initial_sidebar_state="expanded")

# Initialize Global Game Manager (Singleton)
@st.cache_resource
def get_game_manager():
    return GameManager()

game_manager = get_game_manager()

# Initialize Local Session State
if 'session_id' not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4()) # Unique ID for this browser tab
if 'ai_client' not in st.session_state:
    st.session_state.ai_client = None

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
        s.close()
        return IP
    except Exception:
        return "127.0.0.1"

# Inject Custom CSS
def local_css():
    st.markdown("""
    <style>
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    .branding-header { background-color: #374151; color: #f9fafb; padding: 1rem; border-radius: 10px; margin-bottom: 2rem; text-align: center; border-left: 5px solid #ef4444; }
    .context-box { background-color: #1f2937; color: #f9fafb; padding: 20px; border-radius: 10px; margin-bottom: 20px; border: 1px solid #4b5563; }
    .log-box { max-height: 200px; overflow-y: auto; padding: 10px; background-color: #1e1e1e; color: #00ff00; font-family: monospace; border-radius: 5px; font-size: 0.85rem; }
    .role-badge { display: inline-block; padding: 0.2rem 0.5rem; border-radius: 4px; background-color: #3b82f6; color: white; font-weight: bold; margin-right: 0.5rem; }
    .status-acted { color: #10b981; font-weight: bold; }
    .status-waiting { color: #f59e0b; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

local_css()

# --- SIDEBAR CONFIGURATION ---
with st.sidebar:
    st.header("Settings")
    with st.expander("AI Configuration", expanded=True):
        api_key = st.text_input("Gemini API Key", type="password", help="Required for AI generation")
        if api_key:
            st.session_state.ai_client = AIIntegration(api_key)
        else:
            st.session_state.ai_client = AIIntegration(None)

    st.markdown("---")
    st.subheader("Game Status")
    if game_manager.game_started:
        st.success("Game in Progress")
        st.write(f"Turn: {game_manager.current_turn}")
    else:
        st.info("Lobby - Waiting to Start")

# --- MAIN APP FLOW ---

# 1. LOGIN SCREEN
if 'player_name' not in st.session_state:
    st.markdown("<h1 style='text-align: center;'>CrisisSim AI - Multiplayer</h1>", unsafe_allow_html=True)
    with st.form("login_form"):
        name_input = st.text_input("Enter your Name")
        submit_login = st.form_submit_button("Join Lobby")

    if submit_login and name_input:
        st.session_state.player_name = name_input
        # Register player
        game_manager.register_player(st.session_state.session_id, name_input)
        st.rerun()

# 2. LOBBY & ROLE SELECTION
elif not game_manager.game_started:
    st.markdown("<h1 style='text-align: center;'>Lobby</h1>", unsafe_allow_html=True)

    player = game_manager.register_player(st.session_state.session_id, st.session_state.player_name)
    is_host = (game_manager.host_session_id == st.session_state.session_id)

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Scenario Setup (Host Only)")
        if is_host:
            # Load Data
            context_file = st.file_uploader("Upload Context CSV", type=["csv"])
            if context_file:
                try:
                    df = pd.read_csv(context_file)
                    env_text = df.to_string(index=False)

                    # Extract roles
                    roles = extract_roles_from_csv(df)
                    game_manager.set_roles(roles)
                    st.success(f"Loaded {len(roles)} roles: {', '.join(roles)}")

                    # Store env_text in session (Host needs it to start)
                    st.session_state.env_text = env_text

                except Exception as e:
                    st.error(f"Error reading CSV: {e}")

            if st.button("Start Game", disabled=not st.session_state.get('env_text')):
                if not st.session_state.ai_client or not st.session_state.ai_client.client:
                     st.error("AI Key Required")
                else:
                    with st.spinner("Initializing Scenario..."):
                         # Generate start node
                        env_text = st.session_state.env_text
                        json_str = st.session_state.ai_client.generate_initial_node(env_text)

                        if json_str:
                             # Parsing logic similar to before
                            json_str_clean = json_str.strip()
                            if json_str_clean.startswith("```json"): json_str_clean = json_str_clean[7:]
                            if json_str_clean.endswith("```"): json_str_clean = json_str_clean[:-3]
                            try:
                                data = json.loads(json_str_clean)
                                if isinstance(data, list): data = data[0] if len(data) > 0 else {}

                                env_data = data.get("environment")
                                rubric_data = data.get("rubric")
                                start_node_data = data.get("start_node")

                                if env_data and start_node_data:
                                    scenario = Scenario(
                                        environment=Environment(**env_data),
                                        rubric=ScoringRubric(**(rubric_data or {"weights":{}})),
                                        nodes=[Node(**start_node_data)]
                                    )
                                    engine = ScenarioEngine(scenario)
                                    game_manager.start_game(engine)
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Parsing Error: {e}")
        else:
            st.info("Waiting for Host to configure the game...")

    with col2:
        st.subheader("Players Connected")

        # Invite Section
        with st.expander("Invite Players", expanded=True):
            st.info("Share this URL with other players to join the lobby:")

            local_ip = get_local_ip()
            lan_url = f"http://{local_ip}:8501"

            st.markdown("**Local Network (LAN):**")
            st.code(lan_url, language=None)
            st.caption("Use this if players are on the same WiFi.")

            st.markdown("**Localhost (Host only):**")
            st.code("http://localhost:8501", language=None)

            st.warning("⚠️ Ensure your firewall allows incoming connections on port 8501 if connecting from another computer.")

        st.divider()

        # Display list of players
        my_player = game_manager.players.get(st.session_state.session_id)

        # Role Selector
        if game_manager.roles_available:
            selected_role = st.selectbox("Select Your Role", [""] + game_manager.roles_available)
            if selected_role:
                if game_manager.assign_role(st.session_state.session_id, selected_role):
                    st.success(f"Role assigned: {selected_role}")
                else:
                    if my_player.role != selected_role:
                        st.warning("Role taken!")

        st.divider()
        for pid, p in game_manager.players.items():
            role_str = f"[{p.role}]" if p.role else "[No Role]"
            st.write(f"👤 {p.name} {role_str}")

    if st.button("Refresh Lobby"):
        st.rerun()

# 3. GAMEPLAY
else:
    engine = game_manager.engine
    player = game_manager.players.get(st.session_state.session_id)

    if not player or not player.role:
        st.error("You are observing (No Role assigned).")

    current_node = engine.get_current_node()

    # Header
    st.markdown(f"""
    <div class="branding-header">
        <h1>{engine.scenario.environment.branding_title}</h1>
        <p>{engine.scenario.environment.branding_subtitle}</p>
    </div>
    """, unsafe_allow_html=True)

    # Main Content
    col_main, col_side = st.columns([2, 1])

    with col_main:
        # Context
        st.markdown(f"""
        <div class="context-box">
            <h3>Situation Report (Turn {game_manager.current_turn})</h3>
            <p style="font-size: 1.1rem; line-height: 1.6;">{current_node.text}</p>
        </div>
        """, unsafe_allow_html=True)

        # Input Area
        if player and player.role and not player.has_acted:
            st.subheader(f"Your Action: {player.role}")
            with st.form(key=f"action_form_{game_manager.current_turn}"):
                action_text = st.text_area("Describe your decision...", height=100)
                submit = st.form_submit_button("Submit Action")

            if submit and action_text:
                game_manager.submit_action(st.session_state.session_id, action_text)
                st.rerun()
        elif player and player.has_acted:
            st.info("✅ Action submitted. Waiting for other players...")
            st.markdown(f"**Your Action:** {player.last_action}")

    with col_side:
        st.subheader("Team Status")
        all_acted = True
        for pid, p in game_manager.players.items():
            if not p.role: continue
            status = "✅ Ready" if p.has_acted else "⏳ Thinking..."
            if not p.has_acted: all_acted = False
            st.write(f"**{p.role}** ({p.name}): {status}")

        st.markdown("---")
        if st.button("Refresh State"):
            st.rerun()

        # Host Controls to Process Turn
        is_host = (game_manager.host_session_id == st.session_state.session_id)
        if is_host:
            st.subheader("Host Controls")
            if all_acted:
                if st.button("PROCESS TURN >>", type="primary"):
                    # Process Turn Logic
                    with st.spinner("Simulating Consequences..."):
                        actions = game_manager.get_turn_actions()

                        # Construct prompt input from multiple actions
                        action_summary = "\\n".join([f"- {role}: {act}" for role, act in actions.items()])

                        history_str = json.dumps(engine.history[-5:])

                        # Call AI
                        if not st.session_state.ai_client:
                             st.error("Host lost AI connection. Re-enter key.")
                        else:
                            json_str = st.session_state.ai_client.generate_next_node(
                                history_str,
                                current_node.text,
                                action_summary,
                                turn_count=game_manager.current_turn
                            )

                            if json_str:
                                # Parse and Update
                                json_str_clean = json_str.strip()
                                if json_str_clean.startswith("```json"): json_str_clean = json_str_clean[7:]
                                if json_str_clean.endswith("```"): json_str_clean = json_str_clean[:-3]

                                try:
                                    next_node_data = json.loads(json_str_clean)
                                    if isinstance(next_node_data, list): next_node_data = next_node_data[0]

                                    from models import Node
                                    next_node = Node(**next_node_data)
                                    if next_node.id in engine.nodes_map:
                                        next_node.id = f"{next_node.id}_{int(time.time())}"

                                    # Update Engine
                                    engine.add_node(next_node)

                                    # Record history (aggregated)
                                    engine.history.append({
                                        "turn": game_manager.current_turn,
                                        "node_id": current_node.id,
                                        "actions": actions,
                                        "next_node_id": next_node.id
                                    })

                                    # Manually move current node since we don't have a choice index
                                    engine.current_node_id = next_node.id

                                    # Advance Game Manager Turn
                                    game_manager.advance_turn()
                                    st.rerun()

                                except Exception as e:
                                    st.error(f"Error processing turn: {e}")
            else:
                 st.caption("Wait for all players to act.")

    # Shared Log
    st.markdown("---")
    with st.expander("Mission Log"):
        # Custom log display for multiplayer
        for entry in engine.history:
             if "actions" in entry:
                 st.write(f"**Turn {entry.get('turn')}**")
                 st.write("Actions:", entry["actions"])
