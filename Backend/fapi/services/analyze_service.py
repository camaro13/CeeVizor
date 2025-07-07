from ..schemas.analyze import AnalyzeRequest, AnalyzeResponse, StepInfo, VariableInfo, ErrorInfo

def analyze_code(request: AnalyzeRequest) -> AnalyzeResponse:
    # 입력된 C 코드 가져오기 (현재는 사용 안함 - 나중에 파싱용)
    code = request.code

    # ✅ 목업 데이터 구성 (실제 실행 결과가 아님!)
    steps = [
        StepInfo(
            line=2,
            stack=[
                VariableInfo(name="x", type="int", value=3),
                VariableInfo(name="y", type="int", value=4)
            ],
            heap=[],
            data=[]
        ),
        StepInfo(
            line=3,
            stack=[
                VariableInfo(name="x", type="int", value=3),
                VariableInfo(name="y", type="int", value=4)
            ],
            heap=[],
            data=[]
        ),
        StepInfo(
            line=4,
            stack=[
                VariableInfo(name="x", type="int", value=3),
                VariableInfo(name="y", type="int", value=4),
                VariableInfo(name="z", type="int", value=7)
            ],
            heap=[],
            data=[]
        )
    ]

    return AnalyzeResponse(
        steps=steps,
        output="3 + 4 = 7\n",
        error=None
    )
