"""Map data models for the scene graph and exploration tracking."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MapNode(BaseModel):
    """A node in the map representing a navigable scene."""
    id: str = Field(description="Scene ID")
    name: str = Field(description="Display name of the scene")
    description: str = Field(description="Brief description of the scene")
    exits: list[dict[str, str]] = Field(default_factory=list, description="Available exits")
    connections: list[str] = Field(default_factory=list, description="Connected scene IDs")


class MapConnection(BaseModel):
    """A connection between two map nodes."""
    from_node: str = Field(description="Source scene ID")
    to_node: str = Field(description="Target scene ID")
    direction: str = Field(description="Direction of the exit")


class MapState(BaseModel):
    """Current map state including topology and exploration progress."""
    current_node: str = Field(description="Current scene ID where the player is located")
    nodes: list[MapNode] = Field(default_factory=list, description="All available scene nodes")
    connections: list[MapConnection] = Field(default_factory=list, description="Connections between nodes")
    explored_nodes: list[str] = Field(default_factory=list, description="List of scene IDs that have been explored")


class MapResponse(BaseModel):
    """Response model for GET /map endpoint."""
    current_node: str = Field(description="Current scene ID")
    nodes: list[MapNode] = Field(default_factory=list, description="All scene nodes")
    connections: list[MapConnection] = Field(default_factory=list, description="Node connections")
    explored_nodes: list[str] = Field(default_factory=list, description="Explored scene IDs")
