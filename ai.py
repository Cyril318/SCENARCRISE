import os
import json
from typing import Optional
from openai import OpenAI
from models import Scenario

# This is a stub if no API key is provided, or real implementation if provided.
# Since we are in an environment where we might not have a key, we handle gracefully.

class AIIntegration:
    def __init__(self, api_key: Optional[str] = None):
        self.client = OpenAI(api_key=api_key) if api_key else None

    def generate_scenario_from_environment(self, environment_text: str) -> Optional[str]:
        """
        Generates a JSON scenario string based on the environment description.
        """
        if not self.client:
            return None

        prompt = f"""
        Generate a JSON scenario for a crisis simulation based on the following environment:
        "{environment_text}"

        The JSON must adhere to the following structure (schema):
        - environment: {{ branding_title, branding_subtitle, context_description, default_timer }}
        - nodes: list of {{ id, text, image_prompt, type (start, normal, terminal), timer, choices: [ {{ id, text, next_node_id, impacts: [ {{ category, value }} ] }} ] }}
        - rubric: {{ weights: {{ category: weight }} }}

        Ensure there is exactly one 'start' node and at least one 'terminal' node.
        Ensure choices reference valid node IDs.
        Create a branching narrative with at least 5 nodes.
        """

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o", # or gpt-3.5-turbo
                messages=[
                    {"role": "system", "content": "You are a creative scenario designer for a simulation engine."},
                    {"role": "user", "content": prompt}
                ],
                response_format={ "type": "json_object" }
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error generating scenario: {e}")
            return None

    def generate_image(self, prompt: str) -> Optional[str]:
        """
        Generates an image URL based on the prompt.
        """
        if not self.client:
            return "https://placehold.co/600x400?text=No+API+Key"

        try:
            response = self.client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1,
            )
            return response.data[0].url
        except Exception as e:
            print(f"Error generating image: {e}")
            return "https://placehold.co/600x400?text=Image+Generation+Error"
