import streamlit as st
import pandas as pd
import json
import time

from models import Scenario
from engine import ScenarioEngine
from utils import load_json_scenario, load_csv_data
from ai import AIIntegration

# Page Config
st.set_page_config(page_title="CrisisSim AI", layout="wide", initial_sidebar_state="expanded")

# Inject Custom CSS for Ergonomics
def local_css():
    st.markdown("""
    <style>
    /* General Container Styling */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }

    /* Branding Header */
    .branding-header {
        background-color: #374151; /* Dark background */
        color: #f9fafb; /* Light text */
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 2rem;
        text-align: center;
        border-left: 5px solid #ef4444;
    }

    /* Context Box */
    .context-box {
        background-color: #1f2937; /* Dark background */
        color: #f9fafb; /* Light text */
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        margin-bottom: 20px;
        border: 1px solid #4b5563;
    }


    /* Choice Buttons as Cards */
    div.stButton > button {
        width: 100%;
        padding: 0.75rem;
        border-radius: 8px;
        border: 1px solid #4b5563; /* Subtle border for dark mode */
        background-color: #1f2937; /* Dark background */
        color: #ffffff !important; /* Light text */
        text-align: left;
        transition: all 0.2s;
        font-weight: 600;
    }
    div.stButton > button:hover {
        border-color: #ff4b4b;
        background-color: #374151; /* Slightly lighter dark for hover */
        color: #ffffff !important;
        transform: translateY(-2px);
        box-shadow: 0 2px 4px rgba(0,0,0,0.3);
    }
    div.stButton > button:focus {
        color: #ffffff !important;
        border-color: #ff4b4b !important;
    }
    div.stButton > button:active {
        color: #ffffff !important;
        background-color: #4b5563 !important;
    }

    /* Metrics */
    div[data-testid="stMetricValue"] {
        font-size: 2rem;
    }

    /* Log Box */
    .log-box {
        max-height: 200px;
        overflow-y: auto;
        padding: 10px;
        background-color: #1e1e1e;
        color: #00ff00;
        font-family: monospace;
        border-radius: 5px;
        font-size: 0.85rem;
    }
    </style>
    """, unsafe_allow_html=True)

local_css()

# Session State Initialization
if 'engine' not in st.session_state:
    st.session_state.engine = None
if 'ai_client' not in st.session_state:
    st.session_state.ai_client = None
if 'pending_choice' not in st.session_state:
    st.session_state.pending_choice = None

# Sidebar
with st.sidebar:
    st.header("Settings")

    # Gemini Integration
    with st.expander("AI Configuration", expanded=True):
        api_key = st.text_input("Gemini API Key", type="password", help="Required for AI generation")
        if api_key:
            st.session_state.ai_client = AIIntegration(api_key)
        else:
            st.session_state.ai_client = AIIntegration(None)

    # Load Data
    st.subheader("Scenario Loader")
    load_mode = st.radio("Source", ["Use Sample Data", "Upload Files", "Generate with AI"])

    if load_mode == "Upload Files":
        file_type = st.radio("Format", ["JSON", "CSV"], horizontal=True)
        if file_type == "JSON":
            uploaded_file = st.file_uploader("Upload JSON", type="json")
            if uploaded_file and st.button("Load Scenario"):
                try:
                    data = json.load(uploaded_file)
                    with open("temp_scenario.json", "w") as f:
                        json.dump(data, f)
                    scenario = load_json_scenario("temp_scenario.json")
                    st.session_state.engine = ScenarioEngine(scenario)
                    st.success("Loaded successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
        else: # CSV
            env_file = st.file_uploader("Environment CSV", type="csv")
            nodes_file = st.file_uploader("Nodes CSV", type="csv")
            rubric_file = st.file_uploader("Rubric CSV", type="csv")
            if env_file and nodes_file and rubric_file and st.button("Load CSVs"):
                try:
                    env_file.seek(0); pd.read_csv(env_file).to_csv("temp_env.csv", index=False)
                    nodes_file.seek(0); pd.read_csv(nodes_file).to_csv("temp_nodes.csv", index=False)
                    rubric_file.seek(0); pd.read_csv(rubric_file).to_csv("temp_rubric.csv", index=False)
                    scenario = load_csv_data("temp_env.csv", "temp_nodes.csv", "temp_rubric.csv")
                    st.session_state.engine = ScenarioEngine(scenario)
                    st.success("Loaded successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

    elif load_mode == "Use Sample Data":
        if st.button("Load Demo Scenario", type="primary"):
            try:
                scenario = load_json_scenario("data/sample_scenario.json")
                st.session_state.engine = ScenarioEngine(scenario)
                st.success("Demo Loaded!")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

    elif load_mode == "Generate with AI":
        env_text = st.text_area("Describe Scenario Context", height=150, placeholder="e.g. A cyber attack on a hospital...")
        if st.button("Generate", type="primary"):
            if not api_key:
                st.error("Gemini API Key required.")
            else:
                with st.spinner("Initializing scenario..."):
                    # Use new generate_initial_node method
                    json_str = st.session_state.ai_client.generate_initial_node(env_text)

                    if json_str:
                        # Clean string before parsing
                        json_str_clean = json_str.strip()
                        if json_str_clean.startswith("```json"):
                            json_str_clean = json_str_clean[7:]
                        if json_str_clean.endswith("```"):
                            json_str_clean = json_str_clean[:-3]

                        try:
                            data = json.loads(json_str_clean)
                            if isinstance(data, list):
                                if len(data) > 0:
                                    data = data[0]
                                else:
                                    raise ValueError("AI returned an empty list.")

                            # Construct initial scenario structure
                            # Expected from generate_initial_node: { environment, rubric, start_node }

                            env_data = data.get("environment")
                            rubric_data = data.get("rubric")
                            start_node_data = data.get("start_node")

                            if not (env_data and rubric_data and start_node_data):
                                raise ValueError("Missing required fields in initial generation.")

                            # Create Scenario object with just the start node
                            from models import Scenario, Node, Environment, ScoringRubric

                            scenario = Scenario(
                                environment=Environment(**env_data),
                                rubric=ScoringRubric(**rubric_data),
                                nodes=[Node(**start_node_data)]
                            )

                            st.session_state.engine = ScenarioEngine(scenario)
                            st.session_state.dynamic_mode = True # Flag to enable dynamic generation
                            st.success("Scenario Initialized!")
                            st.rerun()

                        except json.JSONDecodeError as e:
                            st.error(f"JSON Error: {e}")
                        except Exception as e:
                            st.error(f"Parsing Error: {e}")
                    else:
                        st.error("Generation failed.")

    st.markdown("---")
    if st.session_state.engine:
        if st.button("Restart Session"):
            st.session_state.engine.reset()
            st.rerun()

        log_text = "\\n".join(st.session_state.engine.log)
        st.download_button("Download Log", log_text, file_name=f"log_{int(time.time())}.txt")

# Main Interface
if st.session_state.engine:
    engine = st.session_state.engine

    # Handle Pending Choice (Dynamic Generation)
    if st.session_state.pending_choice:
        pc = st.session_state.pending_choice
        st.session_state.pending_choice = None # Clear immediately

        # 1. Process the choice in the engine (updates score, history)
        # Note: We need to modify make_choice to NOT fail if next_node_id is missing/dynamic.
        # For now, let's assume the engine allows it or we patch it.
        # Actually, if we use dynamic generation, we generate the NEXT node *before* switching?
        # Or we switch to a temporary ID?

        # Strategy:
        # 1. Generate the next node content using AI.
        # 2. Add the new node to the engine.
        # 3. Update the *current* node's choice to point to this new node ID (retro-active linking).
        # 4. Call engine.make_choice to transition.

        with st.spinner("Analyzing consequences..."):
            # Get context from history
            history_str = json.dumps(engine.history[-5:]) # Last 5 turns
            current_node_text = engine.get_current_node().text
            choice_text = pc["choice_text"]

            # Generate next node
            json_str = st.session_state.ai_client.generate_next_node(history_str, current_node_text, choice_text)

            if json_str:
                # Clean string
                json_str_clean = json_str.strip()
                if json_str_clean.startswith("```json"):
                    json_str_clean = json_str_clean[7:]
                if json_str_clean.endswith("```"):
                    json_str_clean = json_str_clean[:-3]

                try:
                    next_node_data = json.loads(json_str_clean)
                    if isinstance(next_node_data, list): next_node_data = next_node_data[0]

                    from models import Node
                    next_node = Node(**next_node_data)

                    # Ensure unique ID if AI reused generic id
                    if next_node.id in engine.nodes_map:
                        next_node.id = f"{next_node.id}_{int(time.time())}"

                    # Add to engine
                    engine.add_node(next_node)

                    # Link current node choice to this new node
                    # We need to modify the choice object in the engine
                    curr_node = engine.get_current_node()
                    curr_node.choices[pc["choice_idx"]].next_node_id = next_node.id

                    # Now execute the transition
                    engine.make_choice(pc["choice_idx"])
                    st.rerun()

                except Exception as e:
                    st.error(f"Error generating continuation: {e}")
            else:
                st.error("Failed to generate next turn.")

    current_node = engine.get_current_node()
    environment = engine.scenario.environment

    # Removed autorefresh and timer check as per user request
    # Only manual progression via buttons

    # Layout Construction

    # 1. Branding Block
    st.markdown(f"""
    <div class="branding-header">
        <h1>{environment.branding_title}</h1>
        <p style="font-size: 1.2rem; opacity: 0.8;">{environment.branding_subtitle}</p>
    </div>
    """, unsafe_allow_html=True)

    # Main Grid: Left (Context) vs Right (Controls/Stats)
    col_main, col_side = st.columns([2, 1], gap="large")

    with col_main:
        # 2. Context Block (Main)

        # Check if we need to generate content for the current node (if it's missing/placeholder)
        # However, with the current design, we add the node *before* setting it as current.
        # But if the current node is a terminal one generated dynamically, it should be fine.

        st.markdown(f"""
        <div class="context-box">
            <h3>Situation Report</h3>
            <p style="font-size: 1.1rem; line-height: 1.6;">{current_node.text}</p>
        </div>
        """, unsafe_allow_html=True)

    with col_side:
        # Stats Block
        st.markdown("### Status")
        m1, m2 = st.columns(2)
        with m1:
            st.metric("Score", f"{engine.score:.0f}", delta=f"{engine.last_score_delta:+.0f}" if engine.last_score_delta != 0 else None)
        with m2:
            # Show target time instead of countdown
            st.metric("Target Time", f"{current_node.timer}s")

        # 4. Choices Block
        st.markdown("### Decisions")
        if current_node.type == 'terminal':
            st.success("Simulation Concluded")
            st.balloons()
            st.markdown(f"**Final Score:** {engine.score}")
        else:
            for idx, choice in enumerate(current_node.choices):
                # Wrapper for dynamic generation
                def handle_dynamic_choice(choice_idx, choice_text):
                    # 1. Update state (score, log, history) using existing make_choice
                    # Note: make_choice moves current_node_id to next_node_id.
                    # In dynamic mode, next_node_id might be None or a placeholder.

                    # We need a way to intercept the transition.
                    # Since engine.make_choice assumes static graph, we need to modify it or do logic here.
                    # But we can't do async generation in callback easily.
                    # WORKAROUND: We set a flag in session state, and the main loop handles generation.

                    st.session_state.pending_choice = {
                        "node_id": engine.current_node_id,
                        "choice_idx": choice_idx,
                        "choice_text": choice_text
                    }

                # Using callbacks
                st.button(
                    choice.text,
                    key=f"btn_{current_node.id}_{idx}",
                    on_click=handle_dynamic_choice,
                    args=(idx, choice.text)
                )

    # Log Display (Full Width Bottom)
    st.markdown("---")
    with st.expander("Mission Log", expanded=False):
        log_html = "<br>".join([f"> {line}" for line in engine.log])
        st.markdown(f'<div class="log-box">{log_html}</div>', unsafe_allow_html=True)

else:
    # Landing State
    st.markdown("""
    <div style="text-align: center; padding: 50px;">
        <h1>Welcome to CrisisSim AI</h1>
        <p>Initialize a session from the sidebar to begin training.</p>
    </div>
    """, unsafe_allow_html=True)
