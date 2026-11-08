FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-service.txt ./
RUN pip install --no-cache-dir -r requirements-service.txt
COPY agent1 ./agent1
COPY agent1_service ./agent1_service
RUN useradd -m agent && mkdir /state && chown agent:agent /state
USER agent
ENV AGENT1_STATE_DIR=/state AGENT1_THREADS=4 OMP_NUM_THREADS=4
CMD ["uvicorn","agent1_service.main:app","--host","0.0.0.0","--port","8000"]
