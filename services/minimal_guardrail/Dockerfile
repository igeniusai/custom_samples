FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY minimal_guardrail_io_example.py .

EXPOSE 8080

CMD ["uvicorn", "minimal_guardrail_io_example:app", "--host", "0.0.0.0", "--port", "8080"]
