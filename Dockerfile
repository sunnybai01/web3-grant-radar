FROM python:3.11-slim

WORKDIR /app

ENV PIP_NO_CACHE_DIR=1

COPY requirements.runtime.txt constraints.runtime.txt ./
RUN pip install -r requirements.runtime.txt -c constraints.runtime.txt

COPY . .
