# CeeVizor
CeeVizor(Code See Vizor) : Tools for visualizing code execution flows and memory
# 실행방법
1) Docker 설치
   https://docs.docker.com/get-docker/

2) 이미지 받기
   docker pull myid/ceevizor:prod

3) 실행하기
   docker run -d --name ceevizor -p 8000:8000 myid/ceevizor:prod

4) 접속
   브라우저 → http://localhost:8000
