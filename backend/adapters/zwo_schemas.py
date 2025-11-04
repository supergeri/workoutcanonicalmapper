"""Pydantic models for ZWO workout format."""
from pydantic import BaseModel
from typing import Optional, Literal


class Target(BaseModel):
    type: Literal["power", "pace", "hr", "rpe", "none"] = "none"
    min: Optional[float] = None
    max: Optional[float] = None


class Step(BaseModel):
    kind: Literal["steady", "interval", "rest", "warmup", "cooldown"]
    duration_s: Optional[int] = None
    distance_m: Optional[int] = None
    reps: Optional[int] = None
    work_s: Optional[int] = None
    rest_s: Optional[int] = None
    target: Target = Target()


class Workout(BaseModel):
    sport: Literal["run", "ride"]
    name: str
    steps: list[Step]

