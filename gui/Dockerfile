FROM python:3.11-slim

WORKDIR /app

COPY gui/requirements.txt /app/gui/requirements.txt
RUN pip install --no-cache-dir -r /app/gui/requirements.txt

COPY . /app

ENV PYTHONUNBUFFERED=1

EXPOSE 8501

CMD ["bash", "-lc", "PYTHONPATH=. python3 scripts/realtime_gui_server.py --host 0.0.0.0 --port ${GUI_PORT:-8501} --output-root ${GUI_RUNS_DIR:-/app/runs}"]
