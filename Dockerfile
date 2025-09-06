FROM python:3.11-slim

WORKDIR /app

# Install build backend
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

COPY . .

EXPOSE 5000

CMD ["python", "bot.py"]
