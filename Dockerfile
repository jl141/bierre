FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN useradd -m app && chown -R app /app
USER app
EXPOSE 8765
CMD ["python", "webapp/server.py", "--host", "0.0.0.0", "--port", "8765"]
