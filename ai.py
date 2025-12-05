import os
import json
import base64
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

    def generate_scenario_from_environment(self, environment_text: str) -> Optional[str]:
        """
        Generates a JSON scenario string based on the environment description using Gemini (google-genai SDK).
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
        Return ONLY valid JSON.
        """

        try:
            response = self.client.models.generate_content(
                model='gemini-2.0-flash', # Use a capable model
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type='application/json'
                )
            )
            return response.text
        except Exception as e:
            print(f"Error generating scenario with Gemini: {e}")
            return None
