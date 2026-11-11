from typing import List, Tuple
from pydantic import BaseModel, Field


class DifferenceMark(BaseModel):
    id: int
    center_x: int
    center_y: int
    radius: int
    bounding_box: Tuple[int, int, int, int] = Field(
        description="(x, y, width, height)"
    )
    area: float


class DiffResult(BaseModel):
    split_mode: str
    difference_count: int
    differences: List[DifferenceMark]
    execution_time_ms: float
