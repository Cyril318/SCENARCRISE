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
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
        else:
            self.client = None

    def _generate_content_with_fallback(self, prompt: str) -> Optional[str]:
        """Helper method to generate content with model fallback and retry logic."""
        models_to_try = ['gemini-2.0-flash', 'gemini-1.5-flash-001', 'gemini-1.5-flash', 'gemini-1.5-pro']

        for model in models_to_try:
            for attempt in range(3):
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
                    if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                        print(f"Rate limit hit on {model}. Retrying in 10s... (Attempt {attempt+1}/3)")
                        time.sleep(10)
                        continue
                    if "404" in error_str or "NOT_FOUND" in error_str:
                        print(f"Model {model} not found. Trying next model...")
                        break
                    print(f"Error with {model}: {e}")
                    break

        print("All models failed.")
        return None

    def generate_scenario_from_environment(self, environment_text: str) -> Optional[str]:
        """Generates a JSON scenario string based on the environment description."""
        if not self.client:
            return None

        prompt = f"""
        Generate a JSON scenario for a crisis simulation based on the following environment:
        "{environment_text}"

        The JSON must adhere to the following structure (schema):
        {{
          "environment": {{ "branding_title": "string", "branding_subtitle": "string", "context_description": "string", "default_timer": int }},
          "nodes": [ {{
            "id": "string",
            "injects": [ {{ "source": "string", "content": "string", "target_roles": [] }} ],
            "image_prompt": "string",
            "type": "start|normal|terminal",
            "timer": int,
            "choices": []
          }} ],
          "rubric": {{ "weights": {{ "category_name": weight_float }} }}
        }}

        Ensure there is exactly one 'start' node and at least one 'terminal' node.
        Each node must have 2-5 injects (information fragments).
        LANGUAGE: All content MUST be in FRENCH.
        Return ONLY valid JSON.
        """
        return self._generate_content_with_fallback(prompt)

    def generate_initial_node(self, environment_text: str) -> Optional[str]:
        """Generates the initial environment, start node with injects, and system_state."""
        if not self.client:
            return None

        prompt = f"""
        Tu es un ROUTEUR DE CRISE pour une simulation cyndinique.
        Initialise le scenario de crise base sur : "{environment_text}".

        Tu ne generes PAS une narration classique. Tu generes des FRAGMENTS D'INFORMATION (injects)
        provenant de sources differentes, comme dans une vraie cellule de crise.

        Chaque inject a :
        - "source" : l'origine du message (ex: "Standard telephonique", "Temoin sur place", "Radio locale", "Service technique")
        - "content" : le contenu du message (bref, factuel, parfois contradictoire)
        - "target_roles" : liste des roles destinataires. Si vide [], c'est un message public (tous les joueurs le voient).
          Si rempli (ex: ["Pompier"]), SEUL ce role voit le message.

        REGLES CRITIQUES :
        1. Genere entre 3 et 5 injects pour le noeud de depart.
        2. Au moins 1 inject DOIT etre public (target_roles: []).
        3. Au moins 1 inject DOIT etre cible vers un role specifique.
        4. Les informations peuvent etre partielles, vagues ou contradictoires (brouillard de guerre).
        5. Le dernier inject doit contenir un appel a l'action clair.

        Retourne un JSON avec :
        - "environment": {{ "branding_title", "branding_subtitle", "context_description", "default_timer" }}
        - "rubric": {{ "weights": {{ category: weight }} }}
        - "system_state": {{
            "infrastructure_health": float (0-100),
            "public_panic": float (0-100),
            "media_pressure": float (0-100),
            "casualties": int,
            "resources_available": float (0-100),
            "contamination_level": float (0-100)
          }}
        - "start_node": {{
            "id": "start",
            "injects": [
              {{ "source": "...", "content": "...", "target_roles": [] }},
              {{ "source": "...", "content": "...", "target_roles": ["NomDuRole"] }}
            ],
            "image_prompt": "...",
            "type": "start",
            "timer": int,
            "choices": []
          }}

        LANGUE : Tout le contenu (source, content, branding) DOIT etre en FRANCAIS.
        Return ONLY valid JSON.
        """
        return self._generate_content_with_fallback(prompt)

    def generate_next_node(
        self,
        history_context: str,
        current_situation: str,
        applied_actions: str,
        pending_summary: str = "",
        system_state_json: str = "{}",
        turn_count: int = 0,
        random_events_enabled: bool = False,
        inter_player_messages: str = "",
        narrative_memory: str = ""
    ) -> Optional[str]:
        """Generates the next node as a Crisis Router: injects + updated system_state."""
        if not self.client:
            return None

        # --- PHASE LOGIC ---
        if turn_count <= 5:
            current_phase_name = "Phase 1: OBSERVATION & INCERTITUDE"
            phase_context = """
            PHASE 1 : OBSERVATION & INCERTITUDE.
            - Plusieurs sources signalent des anomalies, mais c'est confus.
            - Beaucoup de bruit, peu de signal fiable. Rumeurs et contradictions.
            - Les injects doivent refleter cette confusion : informations partielles,
              sources peu fiables, rapports contradictoires.
            - Ne va pas trop vite. Les metriques systeme bougent lentement.
            """
        elif turn_count <= 12:
            current_phase_name = "Phase 2: ALERTE & MONTEE EN PUISSANCE"
            phase_context = """
            PHASE 2 : ALERTE & MONTEE EN PUISSANCE.
            - Le probleme est identifie, la crise s'amplifie.
            - Les injects deviennent plus urgents et plus nombreux.
            - La pression mediatique monte. Les metriques systeme se degradent significativement.
            - Introduis des demandes de coordination inter-services.
            """
        else:
            current_phase_name = "Phase 3: RESOLUTION & URGENCES"
            phase_context = """
            PHASE 3 : RESOLUTION & URGENCES.
            - Secours et renforts agissent.
            - Les injects refletent les resultats des interventions (succes ou echecs).
            - Consequences a long terme commencent a apparaitre.
            """

        termination_instruction = ""
        if turn_count >= 20:
            termination_instruction = "CRITICAL: C'est le tour 20. Tu DOIS terminer la simulation. Genere un bilan final. Set 'type': 'terminal'."
        elif turn_count >= 15:
            termination_instruction = "NOTE: La simulation approche de sa fin (Tour 20). Commence a converger vers une conclusion."

        random_events_instruction = ""
        if random_events_enabled:
            random_events_instruction = """
            OPTION HOST: Les evenements aleatoires sont ACTIVES.
            Tu peux introduire un inject surprise (meteo, panne, rumeur, accident externe)
            qui n'est pas lie aux actions des joueurs mais complique la situation.
            Cet inject doit avoir une source credible et peut etre cible vers un role specifique.
            """

        # Build narrative memory section
        if narrative_memory:
            memory_section = f"""
        === MEMOIRE NARRATIVE (resume cumulatif de toute la simulation) ===
        {narrative_memory}
        INSTRUCTION CRITIQUE : Tu DOIS maintenir la coherence avec cette memoire.
        Les noms de lieux, personnes, organisations et evenements mentionnes ci-dessus
        sont ETABLIS — ne les change PAS, ne les contredis PAS sauf si l'histoire le justifie
        explicitement (ex: une information se revele fausse)."""
        else:
            memory_section = """
        === MEMOIRE NARRATIVE ===
        (Premier tour — pas encore de memoire. Tu vas l'initialiser avec ton story_summary.)"""

        prompt = f"""
        Tu es un ROUTEUR DE CRISE (pas un narrateur).
        Ton role : generer des FRAGMENTS D'INFORMATION realistes pour la cellule de crise.

        === PHASE ACTUELLE : {current_phase_name} ===
        {phase_context}

        === ETAT SYSTEME CACHE (metriques physiques reelles, invisibles aux joueurs) ===
        {system_state_json}

        {memory_section}

        === REGLES DE COHERENCE NARRATIVE ===
        1. CONTINUITE DES ENTITES : Si un temoin, lieu, batiment, ou organisation a ete
           mentionne dans la memoire narrative, reutilise les MEMES noms exacts.
           Ex: Si "M. Dupont, gardien de l'usine" a ete introduit, ne le renomme pas.
        2. CAUSALITE : Chaque inject doit etre une consequence logique des tours precedents.
           Une action deployee doit avoir un effet visible. Un feu non combattu doit s'aggraver.
        3. EVOLUTION PROGRESSIVE : Les situations evoluent graduellement. Pas de saut brusque
           (ex: un batiment intact ne s'effondre pas soudainement sans signes avant-coureurs).
        4. FILS NARRATIFS : Si un evenement a ete lance (ex: "rumeur de fuite toxique"),
           il doit etre suivi dans les tours suivants (confirme, dementi, ou aggrave).
        5. SOURCES COHERENTES : Les sources recurrentes (CODIS, Mairie, etc.) doivent
           garder un ton et un comportement coherent d'un tour a l'autre.

        === REGLES DU ROUTEUR ===
        1. Genere entre 2 et 5 INJECTS (messages heterogenes provenant de sources differentes).
        2. Chaque inject a une "source" (ex: "CODIS", "Temoin", "Mairie", "Presse locale", "Service technique").
        3. Utilise "target_roles" pour distribuer l'information de maniere ASYMETRIQUE :
           - [] = message public (visible par tous)
           - ["Pompier"] = uniquement visible par le role Pompier
           - ["Maire", "Communication"] = visible par ces deux roles
        4. Les injects peuvent etre CONTRADICTOIRES entre eux (un temoin dit X, un rapport dit Y).
        5. EVALUE les actions deployees. Si bonnes : score positif. Si mauvaises : score negatif.
        6. Mets a jour le system_state en fonction de l'evolution de la crise et des actions deployees.
        7. Les actions "en attente de deploiement" ne sont PAS encore effectives — mentionne-les
           seulement si un role pourrait en avoir connaissance indirecte.

        {random_events_instruction}

        === CONTEXTE ===
        Historique recent (detail des derniers tours):
        {history_context}

        Situation actuelle (injects precedents):
        {current_situation}

        Actions DEPLOYEES ce tour (effet des ordres du tour precedent):
        {applied_actions}

        Actions EN ATTENTE de deploiement (ordres donnes ce tour, pas encore effectifs):
        {pending_summary}

        Communications INTER-JOUEURS (messages echanges entre les roles via radio/telephone):
        {inter_player_messages}
        NOTE: Ces messages montrent le niveau de coordination entre les acteurs de la crise.
        Une bonne coordination devrait avoir un impact positif. Des messages contradictoires
        ou une absence de communication peuvent aggraver la situation.

        {termination_instruction}

        === FORMAT DE REPONSE (JSON STRICT) ===
        {{
          "id": "node_<suffixe_aleatoire>",
          "injects": [
            {{
              "source": "Nom de la source (en Francais)",
              "content": "Contenu du message (en Francais, bref et factuel)",
              "target_roles": []
            }},
            {{
              "source": "Autre source",
              "content": "Information ciblee...",
              "target_roles": ["NomDuRole"]
            }}
          ],
          "system_state": {{
            "infrastructure_health": float,
            "public_panic": float,
            "media_pressure": float,
            "casualties": int,
            "resources_available": float,
            "contamination_level": float
          }},
          "score_delta": float,
          "score_reasoning": "Explication courte de l'impact sur le score (en Francais)...",
          "story_summary": "Resume cumulatif COMPLET de la situation. Inclure : (1) les lieux cles et leur etat, (2) les personnes/entites nommees et leur role, (3) les evenements majeurs et leur statut (en cours/resolu/aggrave), (4) les decisions prises et leurs consequences observees, (5) les fils narratifs ouverts (questions non resolues, menaces en cours). Ce champ REMPLACE la memoire precedente — il doit etre COMPLET et autonome, pas un diff. 3-8 phrases.",
          "image_prompt": "Visual description...",
          "type": "normal",
          "timer": 30,
          "choices": []
        }}

        REGLES FINALES :
        1. Tout le contenu DOIT etre en FRANCAIS.
        2. Ne genere PAS de choices. Retourne [] pour "choices".
        3. score_delta : float positif (bonnes decisions) ou negatif (mauvaises).
        4. Au moins 1 inject public et 1 inject cible par role.
        5. Si la situation doit se terminer, set "type": "terminal".
        6. Le champ "story_summary" est OBLIGATOIRE. Il sert de memoire entre les tours.
        7. Return ONLY valid JSON.
        """
        return self._generate_content_with_fallback(prompt)
