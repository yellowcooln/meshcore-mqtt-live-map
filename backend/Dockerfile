FROM python:3.15.0rc2-slim

ARG APP_VERSION
ENV APP_VERSION=${APP_VERSION}

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends nodejs npm git \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN npm install --prefix /app @michaelhart/meshcore-decoder@0.3.0 \
  && npm cache clean --force

COPY *.py /app/
COPY static /app/static

EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
