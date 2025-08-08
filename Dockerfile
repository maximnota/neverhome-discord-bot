FROM python:3.11-slim

# Ensure logs are shown immediately and Python doesn't write .pyc files
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python dependencies first for better build caching
COPY requirements /app/requirements
RUN pip install --no-cache-dir -r /app/requirements

# Copy the rest of the application code
COPY . /app

# Run the bot
CMD ["python", "-u", "main.py"]


