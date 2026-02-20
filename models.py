from typing import List, Optional, Dict, Literal
from pydantic import BaseModel, Field


class Impact(BaseModel):
    category: str
    value: float


class Choice(BaseModel):
    id: str
    text: str
    next_node_id: Optional[str] = None
    impacts: List[Impact] = []


class SystemState(BaseModel):
    """Hidden physical metrics — not shown to players, only to the AI and spectators."""
    infrastructure_health: float = Field(default=100.0, description="0-100, etat des infrastructures")
    public_panic: float = Field(default=0.0, description="0-100, niveau de panique publique")
    media_pressure: float = Field(default=0.0, description="0-100, pression mediatique")
    casualties: int = Field(default=0, description="Nombre de victimes")
    resources_available: float = Field(default=100.0, description="0-100, ressources disponibles")
    contamination_level: float = Field(default=0.0, description="0-100, niveau de contamination/propagation")
    custom_metrics: Dict[str, float] = Field(default_factory=dict, description="Metriques specifiques au scenario")


class Inject(BaseModel):
    """A fragment of information routed to specific roles (or public)."""
    source: str = Field(description="Origine du message (ex: 'Poste de commandement', 'Temoin', 'Radio locale')")
    content: str = Field(description="Contenu du message")
    target_roles: List[str] = Field(
        default_factory=list,
        description="Si vide = message public. Sinon, restreint a ces roles."
    )


class Node(BaseModel):
    id: str
    injects: List[Inject] = Field(default_factory=list, description="Flux d'information fragmentes par role")
    image_prompt: Optional[str] = None
    type: Literal["start", "normal", "terminal"] = "normal"
    timer: int = 120  # seconds
    choices: List[Choice] = []
    system_state: Optional[SystemState] = None
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
