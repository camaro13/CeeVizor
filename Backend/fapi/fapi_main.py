from fastapi import FastAPI
from pydantic import BaseModel

from Backend.fapi.controller import analyze

app = FastAPI()

class CodeRequest(BaseModel):
    code: str

@app.get("/")
async def root():
    return {"message": "Hello, CeeVizor FastAPI!"}

app.include_router(analyze.router)