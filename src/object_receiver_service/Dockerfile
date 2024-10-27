FROM python:3.9-slim

WORKDIR /app

# Install curl and libmagic for file type detection
RUN apt-get update && \
    apt-get install -y curl libmagic1 && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY object_receiver.py .

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "object_receiver:app", "--host", "0.0.0.0", "--port", "8000"]