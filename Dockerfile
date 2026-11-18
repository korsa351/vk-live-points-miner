FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY VKLivePointsMiner ./VKLivePointsMiner
COPY web ./web
COPY run.py config.example.json ./

EXPOSE 8080

CMD ["python", "-u", "run.py", "--host", "0.0.0.0"]
