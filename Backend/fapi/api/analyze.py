from fastapi import APIRouter, HTTPException
from ..schemas.analyze import AnalyzeRequest, AnalyzeResponse
from ..services.analyze_service import analyze_code

router = APIRouter()

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_endpoint(request: AnalyzeRequest):
    try:
        return analyze_code(request)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
