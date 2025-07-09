# fapi/controller/analyze.py
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

class CodeRequest(BaseModel):
    code: str

@router.post("/analyze")
async def analyze_code(request: CodeRequest):
    # 예시: 받은 코드를 그대로 반환
    return {"received_code": request.code}
