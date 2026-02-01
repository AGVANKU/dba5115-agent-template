from dataclasses import dataclass, field
from typing import Any, Callable
from azure.ai.agents.models import Agent, ToolResources
from azure.ai.agents import AgentsClient


@dataclass
class ManagedAgent:
    """Agent + its local tool executors"""
    agent_client: AgentsClient
    agent: Agent                          # The Azure Agent object
    tool_executors: dict[str, Callable]   # Local Python executors
    
    @property
    def id(self) -> str:
        return self.agent.id
    
    @property
    def tools(self) -> list[dict]:
        return self.agent.tools  # Definitions from Azure
    

@dataclass
class LoadedTools:
    """Tool definitions and executors for an agent.
    
    Can be combined with + operator:
        tools = get_tools(agent_type) + get_knowledge(agent_type)
    """
    definitions: list[dict] = field(default_factory=list)
    executors: dict[str, Callable[..., Any]] = field(default_factory=dict)
    tool_resources: ToolResources | None = None
    
    def __add__(self, other: 'LoadedTools') -> 'LoadedTools':
        """Combine two LoadedTools instances.
        
        Definitions and executors are merged.
        For tool_resources, the first non-None value is used.
        """
        if not isinstance(other, LoadedTools):
            return NotImplemented
        
        # Merge definitions (other first, so knowledge tools come before function tools)
        combined_definitions = (other.definitions or []) + (self.definitions or [])
        
        # Merge executors
        combined_executors = {**(self.executors or {}), **(other.executors or {})}
        
        # First non-None tool_resources wins (knowledge/AI Search takes priority)
        combined_resources = other.tool_resources or self.tool_resources
        
        return LoadedTools(
            definitions=combined_definitions,
            executors=combined_executors,
            tool_resources=combined_resources
        )
    
    
@dataclass
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    thread_messages: int


@dataclass
class NextAction:
    """What the orchestrator should queue next."""
    target_queue: str    # "agent-workflow"
    payload: dict        # Message body for the queue


@dataclass
class AgentWorkflowInput:
    """Standardized input for the workflow activity."""
    agent_type: str      # "email_triage", "student_sp_config", etc.
    payload: dict        # All agent input data (email, student info, etc.)


@dataclass
class AgentResponse:
    """Agent execution result + workflow routing."""
    status: str
    responses: list[dict]
    thread_id: str | None = None
    reason: str | None = None
    usage: TokenUsage | None = None
    tool_calls: int = 0
    inference_rounds: int = 0
    polls: int = 0
    # Workflow additions
    agent_type: str | None = None           # Which agent produced this
    model_name: str | None = None           # Model used by agent
    next_action: NextAction | None = None   # Routing decision for orchestrator
    metadata: dict | None = None            # Agent-provided metadata for analytics

    @classmethod
    def from_dict(cls, data: dict) -> 'AgentResponse':
        """Convert dict (from asdict serialization) back to AgentResponse object."""
        return cls(
            status=data.get("status", "error"),
            responses=data.get("responses", []),
            thread_id=data.get("thread_id"),
            reason=data.get("reason"),
            usage=TokenUsage(**data["usage"]) if data.get("usage") else None,
            tool_calls=data.get("tool_calls", 0),
            inference_rounds=data.get("inference_rounds", 0),
            polls=data.get("polls", 0),
            agent_type=data.get("agent_type"),
            model_name=data.get("model_name"),
            next_action=NextAction(**data["next_action"]) if data.get("next_action") else None,
            metadata=data.get("metadata")
        )