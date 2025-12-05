import os
import json
import base64
import urllib.parse
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
        IMPORTANT: To keep the JSON size manageable, use a converging narrative structure (e.g., bottlenecks where different choices lead to the same next node or a limited set of next nodes).
        Do NOT create a full exponential tree. Limit the TOTAL number of nodes to maximum 50.
        Keep text descriptions concise.
        Return ONLY valid JSON.
        """

        try:
            response = self.client.models.generate_content(
                model='gemini-2.0-flash', # Use a capable model
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type='application/json',
                    max_output_tokens=8192  # Increase token limit for large JSONs (10+ nodes)
                )
            )
            return response.text
        except Exception as e:
            print(f"Error generating scenario with Gemini: {e}")
            return None

    def generate_image(self, prompt: str) -> Optional[str]:
        """
        Generates an image based on the prompt using Imagen via Gemini API.
        """
        if not self.client:
            return "https://placehold.co/600x400?text=No+API+Key"

        try:
            # Try primary model
            model_name = 'imagen-3.0-generate-001'
            try:
                response = self.client.models.generate_images(
                    model=model_name,
                    prompt=prompt,
                    config=types.GenerateImagesConfig(
                        number_of_images=1,
                        aspect_ratio="16:9",
                        include_rai_reason=True
                    )
                )
            except Exception:
                # Fallback to fast model
                model_name = 'imagen-3.0-fast-generate-001'
                response = self.client.models.generate_images(
                    model=model_name,
                    prompt=prompt,
                    config=types.GenerateImagesConfig(
                        number_of_images=1,
                        aspect_ratio="16:9",
                        include_rai_reason=True
                    )
                )

            if response.generated_images:
                image_bytes = response.generated_images[0].image.image_bytes
                b64_img = base64.b64encode(image_bytes).decode('utf-8')
                return f"data:image/png;base64,{b64_img}"

        except Exception as e:
            print(f"Error generating image with Gemini: {e}")
            # Fallback to placeholder if API fails
            safe_prompt = urllib.parse.quote(prompt[:100])
            return f"https://placehold.co/600x400?text={safe_prompt}"

        safe_prompt = urllib.parse.quote(prompt[:100])
        return f"https://placehold.co/600x400?text={safe_prompt}"
