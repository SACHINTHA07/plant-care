FROM python:3.11-slim

WORKDIR /app
RUN pip install --upgrade pip
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY banana_disease_model.keras .
COPY static/ static/
COPY templates/ templates/

EXPOSE 5000


CMD exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 0 app:app
