FROM python:3.14-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY scan_metadata.py .
CMD ["python", "scan_metadata.py"]