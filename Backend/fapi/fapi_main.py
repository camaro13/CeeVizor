
#from fastapi import FastAPI
#from fastapi.middleware.cors import CORSMiddleware
#from .api.analyze import router as analyze_router

#app = FastAPI()

#app.add_middleware(
#    CORSMiddleware,
#    allow_origins=["*"],
#    allow_methods=["*"],
#    allow_headers=["*"],
#)

#app.include_router(analyze_router, prefix="/api")

# 테스트
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from .api.analyze import router as analyze_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze_router, prefix="/api")

# 메인 페이지: C 코드 입력 폼과 결과 표시
@app.get("/", response_class=HTMLResponse)
async def index():
    return """
    <html>
        <head>
            <title>CeeVizor - C 코드 메모리 시각화</title>
        </head>
        <body>
            <h2>C 코드 입력</h2>
            <form action="/analyze" method="post">
                <textarea name="code" rows="10" cols="60">int main() {\n    int x = 3;\n    int y = 4;\n    int z = x + y;\n    return 0;\n}</textarea><br>
                <button type="submit">분석 실행</button>
            </form>
        </body>
    </html>
    """

# 폼에서 POST로 분석 요청 → 결과 HTML로 반환
@app.post("/analyze", response_class=HTMLResponse)
async def analyze_form(code: str = Form(...)):
    # analyze_code 함수 직접 호출 (임포트 필요)
    from .services.analyze_service import analyze_code
    from .schemas.analyze import AnalyzeRequest

    result = analyze_code(AnalyzeRequest(code=code))

    # 결과 HTML 생성
    steps_html = ""
    for i, step in enumerate(result.steps):
        steps_html += f"<h4>Step {i+1} (line {step.line})</h4><ul>"
        steps_html += "<li><b>Stack:</b> " + ", ".join([f"{v.name}={v.value}" for v in step.stack]) + "</li>"
        steps_html += "<li><b>Heap:</b> " + ", ".join([f"{v.name}={v.value}" for v in step.heap]) + "</li>"
        steps_html += "<li><b>Data:</b> " + ", ".join([f"{v.name}={v.value}" for v in step.data]) + "</li>"
        steps_html += "</ul>"

    error_html = f"<p style='color:red;'>{result.error.message}</p>" if result.error else ""
    output_html = f"<pre>{result.output}</pre>"

    return f"""
    <html>
        <head>
            <title>CeeVizor 결과</title>
        </head>
        <body>
            <h2>분석 결과</h2>
            {steps_html}
            <h3>출력 결과</h3>
            {output_html}
            {error_html}
            <a href="/">다시 입력하기</a>
        </body>
    </html>
    """

