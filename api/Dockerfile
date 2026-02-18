FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8443

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8443", \
     "--ssl-certfile", "/etc/veil/certs/server.pem", \
     "--ssl-keyfile", "/etc/veil/certs/key.pem"]
