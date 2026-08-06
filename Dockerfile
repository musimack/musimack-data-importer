FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

WORKDIR /app

RUN addgroup --system musimack && adduser --system --ingroup musimack --no-create-home musimack

COPY requirements.txt ./
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt

COPY src/__init__.py src/config.py src/local_config.py src/profile_aliases.py src/profile_local_config.py ./src/
COPY src/cloud_ingestion ./src/cloud_ingestion
COPY src/providers/__init__.py ./src/providers/__init__.py
COPY src/providers/ga4/__init__.py src/providers/ga4/client.py src/providers/ga4/normalize.py ./src/providers/ga4/
COPY src/providers/gsc/__init__.py src/providers/gsc/client.py ./src/providers/gsc/
COPY scripts/run_cloud_ingestion.py ./scripts/run_cloud_ingestion.py

USER musimack

ENTRYPOINT ["python", "-m", "src.cloud_ingestion.cli"]
