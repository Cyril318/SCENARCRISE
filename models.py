from typing import List, Optional, Dict, Literal
from pydantic import BaseModel, Field, field_validator

class Impact(BaseModel):
    category: str
    value: float

class Choice(BaseModel):
    id: str
    text: str
    next_node_id: Optional[str] = None
    impacts: List[Impact] = []

class Node(BaseModel):
    id: str
    text: str
    image_prompt: Optional[str] = None
    type: Literal["start", "normal", "terminal"] = "normal"
    timer: int = 120  # seconds
    choices: List[Choice] = []
    private_info: Dict[str, str] = {}  # Role -> Private Message
    score_delta: float = 0.0
    score_reasoning: Optional[str] = None

class Environment(BaseModel):
    branding_title: str
    branding_subtitle: str
    context_description: str
    default_timer: int = 120

class ScoringRubric(BaseModel):
    weights: Dict[str, float]

class Scenario(BaseModel):
    environment: Environment
    nodes: List[Node]
    rubric: ScoringRubric
