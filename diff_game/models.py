from typing import List, Tuple, Optional
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
    global_ref_center: Optional[Tuple[int, int]] = None
    global_tgt_center: Optional[Tuple[int, int]] = None


class DiffResult(BaseModel):
    split_mode: str
    difference_count: int
    differences: List[DifferenceMark]
    execution_time_ms: float
    ref_box: Optional[Tuple[int, int, int, int]] = None
    tgt_box: Optional[Tuple[int, int, int, int]] = None
