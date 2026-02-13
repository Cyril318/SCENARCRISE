import json
import pandas as pd
from typing import List, Dict, Optional, Tuple
from models import Scenario, Node, Choice, Impact, Environment, ScoringRubric

def clean_json_string(json_str: str) -> str:
    """
    Cleans a JSON string from AI responses to handle common formatting issues.
    Handles markdown fences, unescaped control characters, and trailing commas.
    """
    import re

    s = json_str.strip()

    # Remove markdown code fences (```json ... ``` or ``` ... ```)
    if s.startswith("```json"):
        s = s[7:]
    elif s.startswith("```"):
        s = s[3:]
    if s.endswith("```"):
        s = s[:-3]
    s = s.strip()

    # If it's already valid JSON, return early
    try:
        json.loads(s)
        return s
    except (json.JSONDecodeError, ValueError):
        pass

    # Remove trailing commas before } or ] (common AI mistake)
    s = re.sub(r',\s*([}\]])', r'\1', s)

    # Escape unescaped control characters inside JSON string values
    # Replace actual newlines/tabs inside strings with escaped versions
    def _escape_control_chars(match):
        content = match.group(0)
        content = content.replace('\n', '\\n')
        content = content.replace('\r', '\\r')
        content = content.replace('\t', '\\t')
        return content

    # Match JSON string values (between double quotes, handling escaped quotes)
    s = re.sub(r'"(?:[^"\\]|\\.)*"', _escape_control_chars, s, flags=re.DOTALL)

    # Final validation attempt
    try:
        json.loads(s)
    except (json.JSONDecodeError, ValueError):
        pass  # Return best-effort cleaned string

    return s

def load_json_scenario(filepath: str) -> Scenario:
    """Loads and validates a scenario from a JSON file."""
    with open(filepath, 'r') as f:
        data = json.load(f)
    scenario = Scenario(**data)
    validate_scenario(scenario)
    return scenario

def validate_scenario(scenario: Scenario, partial: bool = False):
    """
    Validates the scenario graph:
    1. Unique start node.
    2. At least one terminal node (unless partial).
    3. Referencing of nodes in choices (optional but good).
    """
    nodes_by_id = {n.id: n for n in scenario.nodes}

    # 1. Unique start node (not referenced by next) - actually, explicit 'start' type is better
    start_nodes = [n for n in scenario.nodes if n.type == 'start']
    if len(start_nodes) != 1:
        raise ValueError(f"Scenario must have exactly one node with type='start'. Found {len(start_nodes)}.")

    # Strict validation: Start node should not be referenced by any next_node_id
    start_node_id = start_nodes[0].id
    for node in scenario.nodes:
        if node.type != 'terminal':
            for choice in node.choices:
                if choice.next_node_id == start_node_id:
                     raise ValueError(f"Start node '{start_node_id}' is referenced by node '{node.id}', choice '{choice.id}'. Start node must be unique and not referenced.")

    if not partial:
        # 2. At least one terminal node
        terminal_nodes = [n for n in scenario.nodes if n.type == 'terminal']
        if len(terminal_nodes) < 1:
            raise ValueError("Scenario must have at least one node with type='terminal'.")

        # Check node references
        for node in scenario.nodes:
            if node.type != 'terminal':
                for choice in node.choices:
                    if choice.next_node_id and choice.next_node_id not in nodes_by_id:
                         # It's possible to have a terminal choice leading nowhere if handled, but let's warn or error
                         # For now, we allow None for next_node_id if it ends the game or something, but usually it should match.
                         raise ValueError(f"Node {node.id} choice {choice.id} references unknown node {choice.next_node_id}")

def load_csv_data(env_path: str, nodes_path: str, rubric_path: str) -> Scenario:
    """
    Loads scenario from 3 CSV files.
    """
    # Load Environment
    env_df = pd.read_csv(env_path)
    # Assume single row for environment
    env_row = env_df.iloc[0]
    environment = Environment(
        branding_title=env_row.get('branding_title', 'CrisisSim'),
        branding_subtitle=env_row.get('branding_subtitle', 'Simulation'),
        context_description=env_row.get('context_description', 'No context'),
        default_timer=int(env_row.get('default_timer', 30))
    )

    # Load Rubric
    rubric_df = pd.read_csv(rubric_path)
    weights = {}
    for _, row in rubric_df.iterrows():
        weights[row['category']] = float(row['weight'])
    rubric = ScoringRubric(weights=weights)

    # Load Nodes
    # Expect columns: id, text, type, image_prompt, choice1_text, choice1_next, choice1_impact_cat, choice1_impact_val, ...
    # This is a bit complex for CSV flat format, but let's assume a simplified flat structure
    # OR we assume multiple rows per node? The prompt says "Gérer le CSV ENVIRONNEMENT, NOEUDS, RUBRIQUE_SCORING de façon équivalente."
    # Let's assume a flat structure where each node is a row, and choices are columns (choice_1_text, etc) or separate rows.
    # A robust way is one row per node, with JSON strings for choices, OR fixed number of choices.
    # The prompt says "3 choix" in the last line description of CrisisSim. Let's assume 3 choices columns.

    nodes_df = pd.read_csv(nodes_path)
    nodes = []

    for _, row in nodes_df.iterrows():
        choices = []
        for i in range(1, 4):
            c_text = row.get(f'choice_{i}_text')
            c_next = row.get(f'choice_{i}_next')

            # Check if choice exists
            if pd.isna(c_text) or c_text == '':
                continue

            impacts = []
            # Support multiple impacts via semicolon-separated string: "cat1:val1;cat2:val2"
            # OR legacy separate columns for simple single impact.

            # Check for impacts string column first
            c_imp_str = row.get(f'choice_{i}_impacts')
            if not pd.isna(c_imp_str):
                # Parse string "cat:val;cat:val"
                parts = str(c_imp_str).split(';')
                for part in parts:
                    if ':' in part:
                        cat, val = part.split(':', 1)
                        try:
                            impacts.append(Impact(category=cat.strip(), value=float(val.strip())))
                        except ValueError:
                            pass # Handle parsing error gracefully
            else:
                # Fallback to single columns
                c_imp_cat = row.get(f'choice_{i}_impact_category')
                c_imp_val = row.get(f'choice_{i}_impact_value')

                if not pd.isna(c_imp_cat) and not pd.isna(c_imp_val):
                    impacts.append(Impact(category=str(c_imp_cat), value=float(c_imp_val)))

            choices.append(Choice(
                id=f"{row['id']}_c{i}",
                text=str(c_text),
                next_node_id=str(c_next) if not pd.isna(c_next) else None,
                impacts=impacts
            ))

        node = Node(
            id=str(row['id']),
            text=str(row['text']),
            image_prompt=str(row['image_prompt']) if not pd.isna(row.get('image_prompt')) else None,
            type=str(row['type']),
            timer=int(row.get('timer', environment.default_timer)),
            choices=choices
        )
        nodes.append(node)

    scenario = Scenario(environment=environment, nodes=nodes, rubric=rubric)
    validate_scenario(scenario)
    return scenario

def extract_roles_from_csv(df: pd.DataFrame) -> List[str]:
    """
    Extracts playable roles from the context CSV.
    Looks for columns like 'ACTEURS DE LA CRISE', 'Roles', 'Personnages', 'Actors'.
    """
    possible_cols = ['ACTEURS DE LA CRISE', 'Roles', 'Personnages', 'Actors', 'Joueurs']

    roles = []

    # 1. Check for specific columns
    found_col = None
    for col in possible_cols:
        # Case insensitive check
        matches = [c for c in df.columns if c.lower() == col.lower()]
        if matches:
            found_col = matches[0]
            break

    if found_col:
        # If the column exists, we assume it contains a comma-separated list of roles in the first row(s)
        # OR each row is a role?
        # Based on user's previous JSON example: "ACTEURS DE LA CRISE": "Service de sécurité de l'école, directeur, élèves"
        # This implies it's a single cell with a list.

        # Iterate over first few rows to find non-empty value
        for val in df[found_col]:
            if pd.notna(val):
                val_str = str(val)
                # Split by comma
                extracted = [r.strip() for r in val_str.split(',') if r.strip()]
                roles.extend(extracted)
                if roles: break # Found roles, stop looking

    # Deduplicate
    roles = list(set(roles))

    # Fallback if empty
    if not roles:
        roles = ["Directeur", "Responsable Sécurité", "Responsable Communication", "Maire", "Préfet"]

    return sorted(roles)
