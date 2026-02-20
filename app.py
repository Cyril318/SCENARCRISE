import streamlit as st
import pandas as pd
import json
import time
import socket
import uuid

from models import Scenario, Node, Environment, ScoringRubric, Choice, Inject, SystemState
from engine import ScenarioEngine
from utils import load_json_scenario, load_csv_data, extract_roles_from_csv, clean_json_string, migrate_legacy_node_data
from ai import AIIntegration
from gamestate import GameManager
from streamlit_autorefresh import st_autorefresh

# Page Config
st.set_page_config(page_title="CrisisSim AI Multiplayer", layout="wide", initial_sidebar_state="expanded")

def _assess_performance(score: float, num_turns: int) -> tuple:
    """Return (label, severity) based on score normalized by number of turns."""
    if num_turns == 0:
        return ("No data", "info")
    avg_per_turn = score / num_turns
    if avg_per_turn >= 3.0:
        return ("Excellent Crisis Management", "success")
    elif avg_per_turn >= 0.0:
        return ("Acceptable Performance", "warning")
    else:
        return ("Critical Failure", "error")


def display_debriefing(engine, game_manager=None):
    st.markdown("<h1 style='text-align: center; color: #ef4444;'>MISSION DEBRIEFING</h1>", unsafe_allow_html=True)

    num_turns = len(engine.score_history) if engine.score_history else 0

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Final Score", f"{engine.score:.1f}")
        if num_turns > 0:
            st.caption(f"Average per turn: {engine.score / num_turns:+.1f}")

    with col2:
        st.caption("Performance Assessment")
        label, severity = _assess_performance(engine.score, num_turns)
        getattr(st, severity)(label)

    # Score Graph
    if engine.score_history:
        st.subheader("Score Evolution")
        df_score = pd.DataFrame(engine.score_history)
        st.line_chart(df_score, x='turn', y='score')

    # Final System State (full disclosure at debriefing)
    st.divider()
    st.subheader("Etat Final du Systeme")
    state = engine.system_state
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric("Infrastructures", f"{state.infrastructure_health:.0f}%")
        st.metric("Victimes", f"{state.casualties}")
    with col_b:
        st.metric("Panique publique", f"{state.public_panic:.0f}%")
        st.metric("Pression media", f"{state.media_pressure:.0f}%")
    with col_c:
        st.metric("Ressources", f"{state.resources_available:.0f}%")
        st.metric("Contamination", f"{state.contamination_level:.0f}%")

    st.divider()
    st.subheader("Detailed Timeline & Analysis")
    for entry in engine.score_history:
        with st.expander(f"Turn {entry['turn']} (Delta: {entry['delta']:+.1f})", expanded=False):
            st.write(f"**Score:** {entry['score']:.1f}")
            st.info(entry['reasoning'])

    # Export button
    if game_manager:
        st.divider()
        report = game_manager.export_game_report()
        report_json = json.dumps(report, ensure_ascii=False, indent=2)
        st.download_button(
            label="Download Debriefing Report (JSON)",
            data=report_json,
            file_name=f"debriefing_{report.get('title', 'game')}.json",
            mime="application/json"
        )


def display_injects(injects, player_role, is_spectator):
    """Display injects filtered by role with proper formatting.

    Rules:
    1. inject.target_roles is empty -> Public message (everyone sees it)
    2. player.role in inject.target_roles -> Private targeted message
    3. player is spectator -> Sees EVERYTHING (omniscience)
    """
    for inject in injects:
        is_public = not inject.target_roles
        is_targeted_to_me = player_role and player_role in inject.target_roles

        if is_spectator:
            # Spectator omniscience: sees everything with annotation
            if is_public:
                st.info(f"**{inject.source}** : {inject.content}")
            else:
                st.caption(f"👁️ [Vue Spectateur] Message cible pour : {', '.join(inject.target_roles)}")
                st.warning(f"🔒 **{inject.source}** : {inject.content}")
        elif is_public:
            # Public message: visible to all players
            st.info(f"**{inject.source}** : {inject.content}")
        elif is_targeted_to_me:
            # Private message targeted to this player's role
            st.warning(f"🔒 MESSAGE PRIVE - Source: **{inject.source}**\n\n{inject.content}")
        # else: not visible to this player (asymmetric info)


# Initialize Global Game Manager (Singleton)
@st.cache_resource
def get_game_manager():
    return GameManager()

game_manager = get_game_manager()

# Initialize Local Session State
if 'session_id' not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if 'ai_client' not in st.session_state:
    st.session_state.ai_client = None

# Recover player name from query params (survives browser refresh)
_qp = st.query_params
if 'player_name' not in st.session_state and _qp.get("player"):
    recovered_name = _qp["player"]
    st.session_state.player_name = recovered_name
    game_manager.register_player(st.session_state.session_id, recovered_name)

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
        s.close()
        return IP
    except Exception:
        return "127.0.0.1"

def get_public_url():
    """Detect public tunnel URL from environment variable or Streamlit Cloud."""
    import os
    for var in ("PUBLIC_URL", "TUNNEL_URL", "RENDER_EXTERNAL_URL"):
        url = os.environ.get(var)
        if url:
            return url.rstrip("/")
    return None

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
    .inject-public { border-left: 4px solid #3b82f6; padding-left: 10px; margin-bottom: 10px; }
    .inject-private { border-left: 4px solid #f59e0b; padding-left: 10px; margin-bottom: 10px; background-color: #1c1917; }
    .inject-spectator { border-left: 4px solid #8b5cf6; padding-left: 10px; margin-bottom: 10px; opacity: 0.9; }
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
        st.query_params["player"] = name_input
        game_manager.register_player(st.session_state.session_id, name_input)
        st.rerun()

# 2. LOBBY & ROLE SELECTION
elif not game_manager.game_started:
    # Auto-refresh lobby so remote players see updates
    st_autorefresh(interval=8000, limit=None, key="lobby_refresh")

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
                        env_text = st.session_state.env_text
                        json_str = st.session_state.ai_client.generate_initial_node(env_text)

                        if json_str:
                            try:
                                json_str_clean = clean_json_string(json_str)
                                data = json.loads(json_str_clean)
                                if isinstance(data, list): data = data[0] if len(data) > 0 else {}

                                env_data = data.get("environment")
                                rubric_data = data.get("rubric")
                                start_node_data = data.get("start_node")
                                sys_state_data = data.get("system_state")

                                # Backward compatibility: migrate legacy start_node
                                if start_node_data:
                                    start_node_data = migrate_legacy_node_data(start_node_data)

                                if env_data and start_node_data:
                                    # Attach system_state to start node if provided
                                    if sys_state_data:
                                        start_node_data["system_state"] = sys_state_data

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
            st.info("Partagez cette URL aux autres joueurs :")

            public_url = get_public_url()
            if public_url:
                st.markdown("**URL Publique (Reseau universitaire / Internet) :**")
                st.code(public_url, language=None)
                st.success("Les joueurs sur n'importe quel reseau peuvent rejoindre via cette URL.")
            else:
                local_ip = get_local_ip()
                lan_url = f"http://{local_ip}:8501"

                st.markdown("**Reseau local (LAN / meme WiFi) :**")
                st.code(lan_url, language=None)

                st.markdown("**Localhost (hote uniquement) :**")
                st.code("http://localhost:8501", language=None)

                st.divider()
                st.markdown("**Pour un reseau public (universite, etc.) :**")
                st.markdown("""
Lancez un tunnel avec l'une de ces commandes :
```bash
# Option 1 : localtunnel (npm)
npx localtunnel --port 8501

# Option 2 : ngrok
ngrok http 8501

# Option 3 : cloudflared
cloudflared tunnel --url http://localhost:8501
```
Puis definissez la variable d'environnement avant de lancer :
```bash
PUBLIC_URL=https://votre-url.ngrok.io streamlit run app.py
```
                """)
                st.warning("Sur un reseau universitaire, le LAN direct ne fonctionne souvent pas. Utilisez un tunnel.")

        st.divider()

        # Display list of players
        my_player = game_manager.players.get(st.session_state.session_id)

        # Role Selector (+ spectateur option)
        if game_manager.roles_available:
            role_options = [""] + game_manager.roles_available + ["spectateur"]
            selected_role = st.selectbox("Select Your Role", role_options)
            if selected_role:
                if game_manager.assign_role(st.session_state.session_id, selected_role):
                    st.success(f"Role assigned: {selected_role}")
                else:
                    if my_player and my_player.role != selected_role:
                        st.warning("Role taken!")

        st.divider()
        for pid, p in game_manager.players.items():
            role_str = f"[{p.role}]" if p.role else "[No Role]"
            st.write(f"👤 {p.name} {role_str}")

    st.caption("Le lobby se rafraichit automatiquement toutes les 8 secondes.")

# 3. GAMEPLAY
else:
    engine = game_manager.engine
    player = game_manager.players.get(st.session_state.session_id)

    # Late joiner or reconnecting player: register them
    if not player and 'player_name' in st.session_state:
        player = game_manager.register_player(st.session_state.session_id, st.session_state.player_name)

    # Heartbeat & cleanup disconnected players
    game_manager.heartbeat(st.session_state.session_id)
    game_manager.cleanup_disconnected(timeout_seconds=180)

    is_spectator = (player and player.role == "spectateur")
    is_observer = (not player or not player.role)

    if is_observer:
        st.info("Mode Observateur - Vous suivez la partie en lecture seule.")

    current_node = engine.get_current_node()

    if current_node.type == 'terminal':
        display_debriefing(engine, game_manager)

    else:
        # Auto-refresh for sync between players (every 8 seconds)
        count = st_autorefresh(interval=8000, limit=None, key="gameplay_refresh")

        # Timer Logic
        elapsed = time.time() - engine.node_start_time
        remaining = max(0, current_node.timer - int(elapsed))

        # Timeout Handling
        if remaining == 0:
            for pid, p in game_manager.players.items():
                if p.role and p.role != "spectateur" and not p.has_acted:
                    game_manager.submit_action(pid, "[PASSE (TIMEOUT)]")

            if player and player.role and player.role != "spectateur" and not player.has_acted:
                st.rerun()

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
            # Timer Display
            if remaining > 0:
                st.info(f"Temps restant : {remaining} secondes")
            else:
                st.error("TEMPS ECOULE !")

            # === INJECT DISPLAY (Fog of War + Asymmetry) ===
            st.subheader(f"Cellule de Crise - Tour {game_manager.current_turn}")

            player_role = player.role if player else None
            display_injects(current_node.injects, player_role, is_spectator)

            # === SPECTATOR: System State Dashboard (Omniscience) ===
            if is_spectator:
                with st.expander("📊 Etat Systeme (Vue Spectateur)", expanded=True):
                    state = engine.system_state
                    sc1, sc2, sc3 = st.columns(3)
                    with sc1:
                        st.metric("Infrastructures", f"{state.infrastructure_health:.0f}%")
                        st.metric("Victimes", f"{state.casualties}")
                    with sc2:
                        st.metric("Panique", f"{state.public_panic:.0f}%")
                        st.metric("Media", f"{state.media_pressure:.0f}%")
                    with sc3:
                        st.metric("Ressources", f"{state.resources_available:.0f}%")
                        st.metric("Contamination", f"{state.contamination_level:.0f}%")
                    if state.custom_metrics:
                        st.write("**Metriques specifiques:**", state.custom_metrics)

            # Input Area (not for observers or spectators)
            if not is_observer and not is_spectator and player and player.role and not player.has_acted:
                st.subheader(f"Votre Action : {player.role}")
                with st.form(key=f"action_form_{game_manager.current_turn}"):
                    action_text = st.text_area("Decrivez votre decision...", height=100, max_chars=1000)
                    st.caption("⏳ Vos ordres seront deployes au tour suivant (latence de deploiement).")
                    c1, c2 = st.columns([1, 1])
                    with c1:
                        submit = st.form_submit_button("Soumettre", type="primary")
                    with c2:
                        pass_turn = st.form_submit_button("Passer le tour")

                if submit and action_text:
                    game_manager.submit_action(st.session_state.session_id, action_text)
                    st.rerun()
                elif pass_turn:
                    game_manager.submit_action(st.session_state.session_id, "[PASSE]")
                    st.rerun()
            elif not is_observer and not is_spectator and player and player.has_acted:
                st.info("Action soumise. En attente des autres joueurs...")
                st.caption("⏳ Vos ordres seront deployes au prochain tour.")
                st.markdown(f"**Votre action :** {player.last_action}")

        with col_side:
            st.subheader("Cellule de Crise")
            all_acted = True
            for pid, p in game_manager.players.items():
                if not p.role or p.role == "spectateur":
                    continue
                if not p.connected:
                    status = "Deconnecte"
                elif p.has_acted:
                    status = "Pret"
                else:
                    status = "En reflexion..."
                    all_acted = False
                # Players see names/roles (they're in the same crisis cell)
                # but NOT what others decided — only their own status detail
                st.write(f"**{p.role}** ({p.name}): {status}")

            # Actions deployees: filtered by role (fog of war)
            delayed = game_manager.get_turn_actions()
            if delayed:
                if is_spectator:
                    # Spectators see all deployed actions
                    with st.expander("📋 Actions deployees ce tour", expanded=False):
                        for role, act in delayed.items():
                            st.write(f"**{role}:** {act}")
                elif player_role and player_role in delayed:
                    # Regular players only see their own deployed action
                    with st.expander("📋 Votre action deployee ce tour", expanded=False):
                        st.write(f"**{player_role}:** {delayed[player_role]}")
                else:
                    st.caption("Aucune de vos actions deployee ce tour.")
            else:
                st.caption("Aucune action deployee ce tour (premier tour ou pas d'ordres precedents).")

            # === INTER-PLAYER MESSAGING (Radio / Communication) ===
            if not is_observer:
                st.markdown("---")
                st.subheader("📻 Communications")

                # Display received messages for current player
                my_messages = game_manager.get_messages_for_player(st.session_state.session_id)
                current_turn_msgs = [m for m in my_messages if m.turn == game_manager.current_turn]
                older_msgs = [m for m in my_messages if m.turn < game_manager.current_turn]

                if current_turn_msgs:
                    for msg in current_turn_msgs:
                        if msg.target_role == "__ALL__":
                            st.info(f"📻 **{msg.sender_role}** (Radio generale) :\n{msg.content}")
                        elif is_spectator:
                            st.caption(f"👁️ [{msg.sender_role} -> {msg.target_role}]")
                            st.warning(f"📨 **{msg.sender_role}** : {msg.content}")
                        elif msg.sender_role == player_role:
                            st.success(f"📨 Envoye a **{msg.target_role}** : {msg.content}")
                        else:
                            st.warning(f"📨 De **{msg.sender_role}** : {msg.content}")
                else:
                    st.caption("Aucun message ce tour.")

                if older_msgs:
                    with st.expander(f"Messages precedents ({len(older_msgs)})"):
                        for msg in reversed(older_msgs):
                            prefix = f"Tour {msg.turn}"
                            if msg.target_role == "__ALL__":
                                st.caption(f"{prefix} - 📻 {msg.sender_role} (Radio) : {msg.content}")
                            elif msg.sender_role == player_role:
                                st.caption(f"{prefix} - 📨 Envoye a {msg.target_role} : {msg.content}")
                            elif is_spectator:
                                st.caption(f"{prefix} - 👁️ {msg.sender_role} -> {msg.target_role} : {msg.content}")
                            else:
                                st.caption(f"{prefix} - 📨 De {msg.sender_role} : {msg.content}")

                # Send message form (not for spectators or observers)
                if not is_spectator and player and player.role:
                    # Build target list: other active roles + broadcast
                    other_roles = [
                        r for pid, p in game_manager.players.items()
                        if p.role and p.role != "spectateur" and p.role != player.role
                        for r in [p.role]
                    ]
                    # Deduplicate (in case of data issues)
                    other_roles = list(dict.fromkeys(other_roles))
                    target_options = ["Tous (Radio generale)"] + other_roles

                    if target_options:
                        with st.form(key=f"msg_form_{game_manager.current_turn}_{st.session_state.session_id}"):
                            st.markdown("**Envoyer un message**")
                            msg_target = st.selectbox("Destinataire", target_options)
                            msg_content = st.text_input("Message", max_chars=500, placeholder="Votre message...")
                            send_msg = st.form_submit_button("Envoyer")

                        if send_msg and msg_content:
                            target = "__ALL__" if msg_target == "Tous (Radio generale)" else msg_target
                            game_manager.send_message(st.session_state.session_id, target, msg_content)
                            st.rerun()

            st.markdown("---")

            # Host Controls to Process Turn
            is_host = (game_manager.host_session_id == st.session_state.session_id)
            if is_host:
                st.subheader("Host Controls")
                random_events = st.checkbox("Enable Random Events (Injects)", value=False)

                if all_acted:
                    if st.button("PROCESS TURN >>", type="primary"):
                        with st.spinner("Routeur de crise en action..."):
                            error = game_manager.process_turn(
                                st.session_state.ai_client,
                                random_events=random_events
                            )
                            if error:
                                st.error(error)
                            else:
                                st.rerun()
                else:
                    st.caption("Wait for all players to act.")

    # Filtered Mission Log (each player sees only what they know)
    st.markdown("---")
    with st.expander("Journal de Bord"):
        player_role = player.role if player else None
        for entry in engine.history:
            if "injects" in entry:
                turn_num = entry.get('turn')

                # Filter injects: player only sees public + targeted to them
                visible_injects = []
                for inj in entry.get("injects", []):
                    inj_targets = inj.get("target_roles", [])
                    is_public = not inj_targets
                    is_for_me = player_role and player_role in inj_targets

                    if is_spectator or is_public or is_for_me:
                        visible_injects.append(inj)

                if not visible_injects and not is_spectator:
                    continue  # Skip turns where this player saw nothing

                st.write(f"**Tour {turn_num}**")

                # Actions: player only sees their own action (unless spectator)
                applied = entry.get("applied_actions", {})
                if applied:
                    if is_spectator:
                        for role, act in applied.items():
                            st.caption(f"Action deployee [{role}]: {act}")
                    elif player_role and player_role in applied:
                        st.caption(f"Votre action deployee : {applied[player_role]}")

                for inj in visible_injects:
                    inj_targets = inj.get("target_roles", [])
                    if is_spectator and inj_targets:
                        st.caption(f"👁️ [{inj.get('source', '?')} -> {', '.join(inj_targets)}] {inj.get('content', '')}")
                    elif inj_targets:
                        st.caption(f"🔒 [{inj.get('source', '?')}] {inj.get('content', '')}")
                    else:
                        st.caption(f"[{inj.get('source', '?')}] {inj.get('content', '')}")

                # Show inter-player messages for this turn
                turn_messages = game_manager.get_messages_for_turn(turn_num)
                for msg in turn_messages:
                    msg_visible = (
                        is_spectator
                        or msg.target_role == player_role
                        or msg.target_role == "__ALL__"
                        or msg.sender_role == player_role
                    )
                    if msg_visible:
                        if msg.target_role == "__ALL__":
                            st.caption(f"📻 [{msg.sender_role}] (Radio generale): {msg.content}")
                        elif is_spectator:
                            st.caption(f"👁️ 📨 [{msg.sender_role} -> {msg.target_role}]: {msg.content}")
                        else:
                            if msg.sender_role == player_role:
                                st.caption(f"📨 Envoye a {msg.target_role}: {msg.content}")
                            else:
                                st.caption(f"📨 De {msg.sender_role}: {msg.content}")

            elif "actions" in entry:
                # Legacy log format
                st.write(f"**Tour {entry.get('turn')}**")
                if is_spectator:
                    st.write("Actions:", entry["actions"])
