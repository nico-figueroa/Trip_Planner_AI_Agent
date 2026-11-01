FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false
WORKDIR /app
COPY requirements.txt requirements.txt
COPY trip-planner/requirements.txt trip-planner/requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY app.py app.py
COPY trip-planner trip-planner
COPY deploy deploy
RUN python deploy/prepare_model.py && useradd --create-home planner && chown -R planner:planner /app
USER planner
ENV PORT=8000 STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
EXPOSE 8000
CMD ["python", "deploy/start_cloud.py"]
