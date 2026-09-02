FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pipeline/ pipeline/
COPY api/ api/

# Bake a fresh warehouse + dashboard JSON into the image at build time (needs
# network access to the World Bank API during `docker build`). Free hosting
# tiers (e.g. Render) don't offer a persistent disk, so the data can't be
# refreshed in place at runtime — redeploying the image is what refreshes it.
RUN python -m pipeline.main all

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
