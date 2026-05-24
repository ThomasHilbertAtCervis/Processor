FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml ./
COPY processor_playground/ ./processor_playground/

RUN pip install --no-cache-dir .

RUN mkdir -p storage/modules

VOLUME ["/app/storage"]

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "processor_playground.api:app", "--host", "0.0.0.0", "--port", "8000"]
