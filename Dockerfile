# ---------- 1단계: React 빌드 ----------
FROM node:18 AS build
WORKDIR /app/frontend
COPY Frontend/ .
RUN npm install && npm run build

# ---------- 2단계: FastAPI 실행 ----------
FROM python:3.11-slim

# 필수 도구 설치 (gcc, g++, gdb, make)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    gdb \
    make \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 백엔드 복사
COPY Backend/ .

# 프론트엔드 빌드 결과물 복사
COPY --from=build /app/frontend/build ./Frontend/build

# 파이썬 라이브러리 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# FastAPI 실행
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8000"]
