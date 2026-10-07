FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY rosie ./rosie
COPY docs/rosie/system-prompt.md ./docs/rosie/system-prompt.md
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "rosie.main:app", "--host", "0.0.0.0", "--port", "8000"]
