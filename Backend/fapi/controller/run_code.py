from pydantic import BaseModel

class CodeInput(BaseModel):
    language: str
    source_code: str
