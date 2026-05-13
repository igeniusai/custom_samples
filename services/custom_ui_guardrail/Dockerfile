FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY guardrail_custom_ui_blueprint.py admin_ui_template.html ./

EXPOSE 8080

CMD ["uvicorn", "guardrail_custom_ui_blueprint:app", "--host", "0.0.0.0", "--port", "8080"]
