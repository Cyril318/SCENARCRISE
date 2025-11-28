import streamlit as st
import pandas as pd
import json
import time
from streamlit_autorefresh import st_autorefresh

from models import Scenario
from engine import ScenarioEngine
from utils import load_json_scenario, load_csv_data
from ai import AIIntegration

# Page Config
st.set_page_config(page_title="CrisisSim AI", layout="wide")

# Session State Initialization
if 'engine' not in st.session_state:
    st.session_state.engine = None
if 'ai_client' not in st.session_state:
    st.session_state.ai_client = None

# Sidebar
with st.sidebar:
    st.title("Settings")

    # OpenAI Integration
    st.subheader("OpenAI Integration")
    api_key = st.text_input("OpenAI API Key", type="password")
    if api_key:
        st.session_state.ai_client = AIIntegration(api_key)
    else:
        st.session_state.ai_client = AIIntegration(None) # Mock/Stub

    # Load Data
    st.subheader("Load Scenario")
    load_mode = st.radio("Load Mode", ["Upload Files", "Use Sample Data", "Generate with AI"])

    if load_mode == "Upload Files":
        file_type = st.radio("File Type", ["JSON", "CSV"])
        if file_type == "JSON":
            uploaded_file = st.file_uploader("Upload Scenario JSON", type="json")
            if uploaded_file and st.button("Load JSON"):
                try:
                    # Save to temp file or parse directly
                    data = json.load(uploaded_file)
                    # We need to re-validate via models, passing dict to load_json logic?
                    # Let's simplify and just save to a temporary file
                    with open("temp_scenario.json", "w") as f:
                        json.dump(data, f)
                    scenario = load_json_scenario("temp_scenario.json")
                    st.session_state.engine = ScenarioEngine(scenario)
                    st.success("Scenario loaded!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error loading JSON: {e}")
        else: # CSV
            env_file = st.file_uploader("Environment CSV", type="csv")
            nodes_file = st.file_uploader("Nodes CSV", type="csv")
            rubric_file = st.file_uploader("Rubric CSV", type="csv")
            if env_file and nodes_file and rubric_file and st.button("Load CSVs"):
                try:
                    # Save to temp files
                    env_file.seek(0); pd.read_csv(env_file).to_csv("temp_env.csv", index=False)
                    nodes_file.seek(0); pd.read_csv(nodes_file).to_csv("temp_nodes.csv", index=False)
                    rubric_file.seek(0); pd.read_csv(rubric_file).to_csv("temp_rubric.csv", index=False)

                    scenario = load_csv_data("temp_env.csv", "temp_nodes.csv", "temp_rubric.csv")
                    st.session_state.engine = ScenarioEngine(scenario)
                    st.success("Scenario loaded!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error loading CSVs: {e}")

    elif load_mode == "Use Sample Data":
        if st.button("Load Sample"):
            try:
                scenario = load_json_scenario("data/sample_scenario.json")
                st.session_state.engine = ScenarioEngine(scenario)
                st.success("Sample loaded!")
                st.rerun()
            except Exception as e:
                st.error(f"Sample not found or error: {e}")

    elif load_mode == "Generate with AI":
        env_text = st.text_area("Describe the scenario environment")
        if st.button("Generate Scenario"):
            if not api_key:
                st.error("Please provide an OpenAI API Key.")
            else:
                with st.spinner("Generating scenario..."):
                    json_str = st.session_state.ai_client.generate_scenario_from_environment(env_text)
                    if json_str:
                        try:
                            # Parse JSON
                            data = json.loads(json_str)
                            from models import Scenario
                            scenario = Scenario(**data) # Basic validation
                            # Save locally
                            with open("generated_scenario.json", "w") as f:
                                json.dump(data, f)
                            st.session_state.engine = ScenarioEngine(scenario)
                            st.success("Scenario generated and loaded!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error parsing generated JSON: {e}")
                    else:
                        st.error("Failed to generate scenario.")

    st.markdown("---")
    if st.session_state.engine:
        if st.button("Reset Session"):
            st.session_state.engine.reset()
            st.rerun()

        log_text = "\\n".join(st.session_state.engine.log)
        st.download_button("Export Log", log_text, file_name="session_log.txt")

# Main Interface
if st.session_state.engine:
    engine = st.session_state.engine
    current_node = engine.get_current_node()
    environment = engine.scenario.environment

    # Auto-refresh for Timer
    # Refresh every 1 second to update timer display and check timeout
    st_autorefresh(interval=1000, limit=None, key="timer_refresh")

    # Check for timeout
    if engine.check_timer():
        st.rerun()

    # Layout

    # Block 1: Branding
    st.header(environment.branding_title)
    st.subheader(environment.branding_subtitle)

    col1, col2 = st.columns([2, 1])

    with col1:
        # Block 3: Image
        # If AI is enabled and image prompt exists, we could try to generate/fetch,
        # or just use a placeholder if no key.
        # Ideally, we cache images.
        image_url = "https://placehold.co/800x400?text=No+Image"
        if current_node.image_prompt:
            # Here we might want to use the AI client to generate an image
            # But generating on every render is bad (slow + expensive).
            # Should cache it.
            if 'image_cache' not in st.session_state:
                st.session_state.image_cache = {}

            if current_node.id in st.session_state.image_cache:
                image_url = st.session_state.image_cache[current_node.id]
            elif api_key and st.session_state.ai_client:
                 # Generate image if key is present and not cached
                 with st.spinner("Generating Image..."):
                     generated_url = st.session_state.ai_client.generate_image(current_node.image_prompt)
                     if generated_url:
                         st.session_state.image_cache[current_node.id] = generated_url
                         image_url = generated_url

            # Use placeholder text based on prompt if generation failed or no key
            if "placehold.co" in image_url and current_node.image_prompt:
                 # Only replace with text prompt if we haven't successfully generated an image
                 if image_url == "https://placehold.co/800x400?text=No+Image":
                     image_url = f"https://placehold.co/800x400?text={current_node.image_prompt.replace(' ', '+')}"

        st.image(image_url, use_container_width=True)

        # Block 2: Context
        st.markdown("### Context")
        st.write(current_node.text)

    with col2:
        # Score and Timer
        st.metric("Score", f"{engine.score:.2f}")

        elapsed = time.time() - engine.node_start_time
        remaining = max(0, current_node.timer - int(elapsed))
        st.metric("Time Remaining", f"{remaining}s")
        st.progress(min(1.0, elapsed / current_node.timer) if current_node.timer > 0 else 0)

        # Block 4: Choices
        st.markdown("### Choices")
        if current_node.type == 'terminal':
            st.info("Scenario Ended.")
            st.balloons()
        else:
            for idx, choice in enumerate(current_node.choices):
                if st.button(choice.text, key=f"choice_{choice.id}"):
                    engine.make_choice(idx)
                    st.rerun()

    # Log Display
    with st.expander("Session Log", expanded=False):
        for entry in engine.log:
            st.text(entry)

else:
    st.info("Please load a scenario from the sidebar.")
    # Show instructions
    st.markdown("""
    ## Welcome to CrisisSim AI

    To get started:
    1. Open the sidebar.
    2. Choose **Load Mode**.
    3. Click **Load Sample** to see a demo, or upload your own files.
    """)
