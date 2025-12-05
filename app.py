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

    /* Image Container */
    .image-container img {
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
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
                with st.spinner("AI is crafting your scenario..."):
                    json_str = st.session_state.ai_client.generate_scenario_from_environment(env_text)
                    if json_str:
                        try:
                            data = json.loads(json_str)
                            # Handle potential list wrapping by LLM
                            if isinstance(data, list):
                                if len(data) > 0 and isinstance(data[0], dict):
                                    data = data[0]
                                else:
                                    raise ValueError("Received a JSON list but expected a Scenario object.")

                            from models import Scenario
                            scenario = Scenario(**data)
                            with open("generated_scenario.json", "w") as f:
                                json.dump(data, f)
                            st.session_state.engine = ScenarioEngine(scenario)
                            st.success("Generated!")
                            st.rerun()
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

    # Main Grid: Left (Media/Context) vs Right (Controls/Stats)
    col_main, col_side = st.columns([2, 1], gap="large")

    with col_main:
        # 3. Image Block (Top of Main)
        image_url = "https://placehold.co/800x400?text=No+Image"
        if current_node.image_prompt:
            if 'image_cache' not in st.session_state:
                st.session_state.image_cache = {}

            if current_node.id in st.session_state.image_cache:
                image_url = st.session_state.image_cache[current_node.id]
            elif st.session_state.ai_client and st.session_state.ai_client.api_key:
                 with st.spinner("Visualizing..."):
                     generated_url = st.session_state.ai_client.generate_image(current_node.image_prompt)
                     if generated_url:
                         st.session_state.image_cache[current_node.id] = generated_url
                         image_url = generated_url

            # Fallback to placeholder if not generated
            if "placehold.co" in image_url and current_node.image_prompt:
                 if image_url == "https://placehold.co/800x400?text=No+Image":
                     image_url = f"https://placehold.co/800x400?text={current_node.image_prompt.replace(' ', '+')}"

        st.markdown('<div class="image-container">', unsafe_allow_html=True)
        st.image(image_url)
        st.markdown('</div>', unsafe_allow_html=True)

        # 2. Context Block (Bottom of Main)
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
                # Using callbacks to ensure button clicks are processed reliably despite autorefresh
                st.button(
                    choice.text,
                    key=f"btn_{current_node.id}_{idx}",
                    on_click=engine.make_choice,
                    args=(idx,)
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
