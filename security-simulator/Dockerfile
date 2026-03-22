FROM python:3.11-slim

WORKDIR /app

COPY security-simulator/requirements.txt /app/security-simulator/requirements.txt
RUN pip install --no-cache-dir -r /app/security-simulator/requirements.txt

COPY . /app

ENV PYTHONUNBUFFERED=1

EXPOSE 8090

CMD ["bash", "-lc", "PYTHONPATH=. python3 scripts/security_server.py --host 0.0.0.0 --port ${SECURITY_PORT:-8090} --output-root ${SECURITY_RUNS_DIR:-/app/runs/security}"]
