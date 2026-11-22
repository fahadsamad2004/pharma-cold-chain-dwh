# One image reused by Airflow, the ingestion API and the file watcher.
FROM apache/airflow:2.10.5-python3.11
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
