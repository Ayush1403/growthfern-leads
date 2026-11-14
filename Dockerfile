FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY leads.py .
ENV DB_PATH=/data/leads.db PYTHONUNBUFFERED=1
VOLUME /data
CMD ["python", "leads.py"]
