import os
import json
import base64
import urllib.parse
import time
from typing import Optional
from google import genai
from google.genai import types
from models import Scenario

class AIIntegration:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        # Initialize the new client.
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None

    def _generate_content_with_fallback(self, prompt: str) -> Optional[str]:
        """
        Helper method to generate content with model fallback and retry logic.
        """
        models_to_try = ['gemini-2.0-flash', 'gemini-1.5-flash-001', 'gemini-1.5-flash', 'gemini-1.5-pro']

        for model in models_to_try:
            for attempt in range(3): # Retry logic per model
                try:
                    response = self.client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=types.GenerateContentConfig(
                            response_mime_type='application/json',
                            max_output_tokens=8192
                        )
                    )
                    return response.text
                except Exception as e:
                    error_str = str(e)
                    # Handle Rate Limits (429) by waiting and retrying the SAME model
                    if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                        print(f"Rate limit hit on {model}. Retrying in 10s... (Attempt {attempt+1}/3)")
                        time.sleep(10)
                        continue # Retry same model

                    # Handle Not Found (404) or other client errors by switching to NEXT model
                    if "404" in error_str or "NOT_FOUND" in error_str:
                        print(f"Model {model} not found. Trying next model...")
                        break # Break retry loop, go to next model

                    # Other errors -> likely unrecoverable for this model or prompt issue
                    print(f"Error with {model}: {e}")
                    break # Break retry loop, try next model just in case? Or stop?
                          # Safer to try next model.

        print("All models failed.")
        return None

    def generate_scenario_from_environment(self, environment_text: str) -> Optional[str]:
        """
        Generates a JSON scenario string based on the environment description using Gemini.
        """
        if not self.client:
            return None

        prompt = f"""
        Generate a JSON scenario for a crisis simulation based on the following environment:
        "{environment_text}"

        The JSON must adhere to the following structure (schema):
        {{
          "environment": {{ "branding_title": "string", "branding_subtitle": "string", "context_description": "string", "default_timer": int }},
          "nodes": [ {{ "id": "string", "text": "string", "image_prompt": "string", "type": "start|normal|terminal", "timer": int, "choices": [ {{ "id": "string", "text": "string", "next_node_id": "string", "impacts": [ {{ "category": "string", "value": int }} ] }} ] }} ],
          "rubric": {{ "weights": {{ "category_name": weight_float }} }}
        }}

        Ensure there is exactly one 'start' node and at least one 'terminal' node.
        Ensure choices reference valid node IDs.
        Create a branching narrative where the user plays for at least 10 turns (depth >= 10) regardless of their choices.
        IMPORTANT: To keep the JSON size manageable, use a converging narrative structure (e.g., bottlenecks where different choices lead to the same next node or a limited set of next nodes).
        Do NOT create a full exponential tree. Limit the TOTAL number of nodes to maximum 50.
        Keep text descriptions concise.
        Return ONLY valid JSON.
        """
        return self._generate_content_with_fallback(prompt)

    def generate_initial_node(self, environment_text: str) -> Optional[str]:
        """
        Generates the initial environment and start node for a dynamic scenario.
        """
        if not self.client:
            return None

        prompt = f"""
        Initialize a dynamic crisis simulation scenario based on: "{environment_text}".

        You are generating the start of a simulation where the user can type any action.
        Therefore, the "start_node" should describe the initial inject/event.
        IMPORTANT: Do NOT generate specific choices for the user. The user will type their own action.
        However, the schema requires a "choices" list. Please return an EMPTY list [] for "choices" in the start node.

        Return a JSON object with:
        - "environment": {{ "branding_title", "branding_subtitle", "context_description", "default_timer" }}
        - "rubric": {{ "weights": {{ category: weight }} }}
        - "start_node": {{
            "id": "start",
            "text": "Description de la situation initiale (en Français)...",
            "image_prompt": "...",
            "type": "start",
            "timer": int,
            "choices": []
        }}

        LANGUAGE: The "text", "branding_title", etc. MUST be in FRENCH.
        Keep descriptions concise.
        Return ONLY valid JSON.
        """
        return self._generate_content_with_fallback(prompt)

    def generate_next_node(self, history_context: str, current_node_text: str, choice_text: str, turn_count: int = 0) -> Optional[str]:
        """
        Generates the next node based on the user's choice (or multiple users' actions).
        """
        if not self.client:
            return None

        # Logic to enforce termination around 20 turns
        termination_instruction = ""
        if turn_count >= 20:
            termination_instruction = "CRITICAL: This is the 20th turn. You MUST end the simulation now. Generate a conclusion based on the user's performance. Set 'type': 'terminal'."
        elif turn_count >= 15:
            termination_instruction = "NOTE: The simulation is approaching its end (Turn 20). Start wrapping up the narrative and converging towards a conclusion."

        # Handle multiple actions (Multiplayer)
        # If choice_text is a formatted string of multiple actions, the prompt adapts nicely.
        actions_description = choice_text

        prompt = f"""
        Continue the crisis simulation (Multiplayer). Turn {turn_count + 1}.

        Context/History:
        {history_context}

        Current Situation: "{current_node_text}"

        User Actions (Team):
        {actions_description}

        Analyze the collective actions of the players (different roles) and generate the consolidated consequences (the next inject/event).
        Consider how different actions might conflict or synergize.

        {termination_instruction}

        Return a JSON object for the NEXT node:
        {{
          "id": "node_<random_suffix>",
          "text": "Conséquences des actions collectives et nouvelle situation (en Français)...",
          "image_prompt": "Visual description...",
          "type": "normal",
          "timer": 30,
          "choices": []
        }}

        IMPORTANT:
        1. The content (text) MUST be in FRENCH.
        2. Do NOT generate choices. The user will type their next action freely. Return an empty list [] for "choices".
        3. Even though there are no choices, you can still estimate the impact of the USER'S ACTION on the score.
           However, since the schema puts impacts on choices, we cannot easily return impacts here without a dummy choice.
           WORKAROUND: Return a single dummy choice in the list ONLY if you need to apply a score impact, otherwise empty.
           Actually, let's keep it simple: Return an EMPTY choices list. We will rely on the narrative for now.

        If the story should end, set "type": "terminal".
        Keep it concise.
        Return ONLY valid JSON.
        """
        return self._generate_content_with_fallback(prompt)
