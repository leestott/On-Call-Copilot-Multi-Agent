# Matches the official foundry-samples Dockerfile pattern
# Ref: github.com/microsoft-foundry/foundry-samples/.../agent-with-foundry-tools/Dockerfile
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . user_agent/
WORKDIR /app/user_agent

EXPOSE 8088

CMD ["python", "main.py"]
