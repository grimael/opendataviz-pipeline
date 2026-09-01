FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pipeline/ pipeline/
COPY api/ api/
RUN mkdir -p data dashboard/data
# data/ and dashboard/data/ are mounted as volumes at run time (see README) —
# they change daily via the ETL cron and shouldn't be baked into the image.

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
