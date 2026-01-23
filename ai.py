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

        CRITICAL INSTRUCTION: The text description of the node MUST end with a clear Call to Action or a situation requiring intervention from at least one of the players/roles.

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

    def generate_next_node(self, history_context: str, current_node_text: str, choice_text: str, turn_count: int = 0, random_events_enabled: bool = False) -> Optional[str]:
        """
        Generates the next node based on the user's choice (or multiple users' actions).
        """
        if not self.client:
            return None

        # --- PHASE LOGIC ---
        # Determine current phase based on turn count
        phase_context = ""
        current_phase_name = ""

        if turn_count <= 5:
            current_phase_name = "Phase 1: OBSERVATION & INCERTITUDE"
            phase_context = """
            🔵 PHASE 1 : OBSERVATION & INCERTITUDE.
            - Plusieurs acteurs signalent quelque chose de suspect, mais c'est flou.
            - Il y a de l'incertitude, des rumeurs, des "bruits faibles".
            - Ce n'est pas encore la panique, mais l'incompréhension domine.
            - NE PARLE PAS TOUT DE SUITE DES PARENTS/MEDIA sauf si nécessaire.
            - Pose le décor, montre des dysfonctionnements isolés qui ne font pas encore "crise".
            """
        elif turn_count <= 12:
            current_phase_name = "Phase 2: ALERTE & MONTÉE EN PUISSANCE"
            phase_context = """
            🟠 PHASE 2 : ALERTE & MONTÉE EN PUISSANCE.
            - Le problème est identifié et commence à prendre de l'envergure.
            - La panique se fait ressentir.
            - Les acteurs sont sous pression et peuvent prendre de MAUVAISES DÉCISIONS.
            - Les impacts s'aggravent (ex: panne réseau -> plus de mail -> décision bloquée).
            """
        else:
            current_phase_name = "Phase 3: RÉSOLUTION & URGENCES"
            phase_context = """
            🔴 PHASE 3 : RÉSOLUTION & URGENCES.
            - Les secours/renforts arrivent ou agissent.
            - Les solutions techniques ou humaines sont déployées (avec plus ou moins de succès).
            - On gère les conséquences ultimes.
            """

        # Logic to enforce termination around 20 turns
        termination_instruction = ""
        if turn_count >= 20:
            termination_instruction = "CRITICAL: This is the 20th turn. You MUST end the simulation now. Generate a conclusion (debriefing) based on the user's performance. Set 'type': 'terminal'."
        elif turn_count >= 15:
            termination_instruction = "NOTE: The simulation is approaching its end (Turn 20). Start wrapping up the narrative and converging towards a conclusion."

        # Random Events
        random_events_instruction = ""
        if random_events_enabled:
             random_events_instruction = """
             OPTION HOST: Les événements aléatoires sont ACTIVÉS.
             Tu peux, si tu le juges pertinent pour le rythme, introduire un "Inject Surprise" (ex: Météo, Panne, Rumeur, Accident externe) qui n'est pas directement lié aux actions des joueurs mais qui complique la situation.
             """

        # Handle multiple actions (Multiplayer)
        actions_description = choice_text

        prompt = f"""
        Tu es un Scénariste de Crise Expert (MEL).
        Génère la suite de la simulation (Tour {turn_count + 1}).

        === PHASE ACTUELLE : {current_phase_name} ===
        {phase_context}

        === RÈGLES D'OR (CRITIQUES) ===
        1. *Début de la crise* : Ne va pas trop vite. Montre les signaux faibles avant la crise majeure.
        2. *DESTINATAIRES* : Le texte doit s'adresser aux acteurs présents dans le contexte.
        3. *CONTINUITÉ & PROFONDEUR* : Décris les IMPACTS EN CASCADE. (Ex: Panne -> Pas de mail -> Décision bloquée).
        4. *COHÉRENCE TEMPORELLE* : Assure-toi que les événements suivent une logique temporelle par rapport à l'historique.
        5. *SCORING* : Évalue les actions des joueurs. Si elles sont bonnes (cohérentes, proactives), donne un score positif. Si elles sont mauvaises (passives, dangereuses), score négatif.
        6. *STYLE FACTUEL & IMPERSONNEL* : Dans le champ "text" (Public), sois FACTUEL. Ne nomme pas spécifiquement qui a fait quoi sauf si c'est indispensable. Décris les conséquences de manière objective (Ex: "Une évacuation a été ordonnée" au lieu de "Le Maire a ordonné...").
        7. *COMMUNICATIONS PRIVÉES* : Si un joueur envoie un message ou une information à un autre rôle spécifique (ex: "J'appelle le Maire"), tu DOIS mettre le contenu de ce message dans le champ `private_info` du DESTINATAIRE (Le Maire), pour simuler la réception de l'info.

        {random_events_instruction}

        Context/History:
        {history_context}

        Current Situation: "{current_node_text}"

        User Actions (Team):
        {actions_description}

        Analyse les actions collectives et génère la suite (conséquences + nouveaux événements).
        Si l'action est "[PASSE]", le joueur est passif.

        {termination_instruction}

        CRITICAL INSTRUCTION:
        1. The text description of the node MUST end with a clear Call to Action or a situation requiring intervention from at least one of the players/roles.
        2. Generate PRIVATE INFORMATION for specific roles if they would notice something others wouldn't, or if they are in a specific location.

        Return a JSON object for the NEXT node:
        {{
          "id": "node_<random_suffix>",
          "text": "Conséquences des actions collectives et nouvelle situation (en Français) - PUBLIC INFORMATION...",
          "private_info": {{
              "Role Name": "Information privée spécifique à ce rôle (en Français)...",
              "Another Role": "Autre info..."
          }},
          "score_delta": 0.0,
          "score_reasoning": "Explication courte de l'impact sur le score...",
          "image_prompt": "Visual description...",
          "type": "normal",
          "timer": 30,
          "choices": []
        }}

        IMPORTANT:
        1. The content (text, private_info, score_reasoning) MUST be in FRENCH.
        2. Do NOT generate choices. The user will type their next action freely. Return an empty list [] for "choices".
        3. `score_delta` should be a float (e.g., 5.0, -10.0, 0.0). Positive for good crisis management, negative for mistakes.

        If the story should end, set "type": "terminal".
        Keep it concise.
        Return ONLY valid JSON.
        """
        return self._generate_content_with_fallback(prompt)
