from typing import List, Optional, Dict
from pydantic import BaseModel, Field, validator

class Impact(BaseModel):
    category: str
    value: int

class Choice(BaseModel):
    id: str
    text: str
    next_node_id: Optional[str] = None
    impacts: List[Impact] = []

class Node(BaseModel):
    id: str
    text: str
    image_prompt: Optional[str] = None
    type: str = "normal"  # start, normal, terminal
    timer: int = 30  # seconds
    choices: List[Choice] = []

    @validator('type')
    def validate_type(cls, v):
        if v not in ['start', 'normal', 'terminal']:
            raise ValueError('type must be one of start, normal, terminal')
        return v

class Environment(BaseModel):
    branding_title: str
    branding_subtitle: str
    context_description: str
    default_timer: int = 30

class ScoringRubric(BaseModel):
    weights: Dict[str, float]

class Scenario(BaseModel):
    environment: Environment
    nodes: List[Node]
    rubric: ScoringRubric
