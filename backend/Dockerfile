FROM node:24.22.1-trixie-slim AS node-assets
WORKDIR /assets
COPY package.json package-lock.json ./
COPY scripts ./scripts
RUN npm ci --omit=dev --no-audit --fund=false \
  && npm run build:assets

FROM python:3.15.1-slim

ARG APP_VERSION=1.9.8
ENV APP_VERSION=${APP_VERSION}

WORKDIR /app

# Official Node and Python stages share Debian trixie/glibc. Retain only the
# Node executable and its runtime libraries; npm 11 stays in the build stage.
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    git libstdc++6 libatomic1 tzdata \
  && rm -rf /var/lib/apt/lists/*
COPY --from=node-assets /usr/local/bin/node /usr/local/bin/node
COPY --from=node-assets /assets/node_modules /app/node_modules
RUN node --version \
  && node --input-type=module -e "await import('@michaelhart/meshcore-decoder')"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py /app/
COPY static /app/static
COPY --from=node-assets /assets/static/vendor /app/static/vendor

EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
