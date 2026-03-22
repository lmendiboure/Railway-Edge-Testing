FROM python:3.11-slim

WORKDIR /app

COPY security-gui/requirements.txt /app/security-gui/requirements.txt
RUN pip install --no-cache-dir -r /app/security-gui/requirements.txt

COPY . /app

ENV PYTHONUNBUFFERED=1

EXPOSE 8601

CMD ["bash", "-lc", "PYTHONPATH=. python3 scripts/security_gui_server.py --host 0.0.0.0 --port ${SECURITY_GUI_PORT:-8601} --output-root ${SECURITY_RUNS_DIR:-/app/runs/security}"]
