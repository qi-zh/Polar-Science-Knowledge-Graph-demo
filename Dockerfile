FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md main.py ./
COPY src ./src
COPY data ./data

RUN pip install --no-cache-dir .

CMD ["python", "main.py", "--mode", "frozen", "--reset-db"]
