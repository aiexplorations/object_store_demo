FROM python:3.9-slim

WORKDIR /app

# Install required system packages
RUN apt-get update && \
    apt-get install -y curl libmagic1 && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application
COPY orchestrator.py .

# Expose the port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "orchestrator:app", "--host", "0.0.0.0", "--port", "8000"]
