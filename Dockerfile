# Copyright (C) 2026 Dasik (Rifaditya) | GNU GPLv3
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY warden.py warden_core.py ./

CMD ["python", "warden.py"]
