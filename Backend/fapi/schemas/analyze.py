from pydantic import BaseModel
from typing import List, Optional, Union

class VariableInfo(BaseModel):
    name: str
    type: str
    value: Union[int, str, None]

class StepInfo(BaseModel):
    line: int
    stack: List[VariableInfo]
    heap: List[VariableInfo]
    data: List[VariableInfo]

class ErrorInfo(BaseModel):
    line: int
    message: str

class AnalyzeRequest(BaseModel):
    code: str

class AnalyzeResponse(BaseModel):
    steps: List[StepInfo]
    output: str
    error: Optional[ErrorInfo] = None
