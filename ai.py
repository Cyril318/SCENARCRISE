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

        Return a JSON object with:
        - "environment": {{ "branding_title", "branding_subtitle", "context_description", "default_timer" }}
        - "rubric": {{ "weights": {{ category: weight }} }}
        - "start_node": {{
            "id": "start",
            "text": "Initial situation description...",
            "image_prompt": "...",
            "type": "start",
            "timer": int,
            "choices": [
                {{
                    "id": "c1",
                    "text": "...",
                    "impacts": [ {{ "category": "CategoryName", "value": 5.0 }} ]
                }}
            ]
        }}

        IMPORTANT: 'impacts' must be a LIST OF OBJECTS, not strings. Each object must have "category" (string) and "value" (number).
        Note: The choices in 'start_node' do NOT need 'next_node_id' as they will be generated dynamically.
        Keep descriptions concise.
        Return ONLY valid JSON.
        """
        return self._generate_content_with_fallback(prompt)

    def generate_next_node(self, history_context: str, current_node_text: str, choice_text: str) -> Optional[str]:
        """
        Generates the next node based on the user's choice.
        """
        if not self.client:
            return None

        prompt = f"""
        Continue the crisis simulation.

        Context/History:
        {history_context}

        Current Situation: "{current_node_text}"
        User Choice: "{choice_text}"

        Generate the consequences and the next node.
        Return a JSON object for the NEXT node:
        {{
          "id": "node_<random_suffix>",
          "text": "Consequence description and new situation...",
          "image_prompt": "Visual description...",
          "type": "normal",
          "timer": 30,
          "choices": [
             {{ "id": "c1", "text": "Action 1...", "impacts": [ {{ "category": "CategoryName", "value": 5.0 }} ] }},
             {{ "id": "c2", "text": "Action 2...", "impacts": [ {{ "category": "CategoryName", "value": -2.0 }} ] }},
             {{ "id": "c3", "text": "Action 3...", "impacts": [...] }}
          ]
        }}

        IMPORTANT: 'impacts' must be a LIST OF OBJECTS with "category" and "value". Do NOT use strings.
        If the story should end, set "type": "terminal" and "choices": [].
        Keep it concise.
        Return ONLY valid JSON.
        """
        return self._generate_content_with_fallback(prompt)
