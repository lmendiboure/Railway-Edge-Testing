FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["bash", "-lc", "PYTHONPATH=. python3 scripts/realtime_server.py --host 0.0.0.0 --port ${SIM_PORT:-8080}"]
