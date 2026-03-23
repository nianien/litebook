#!/bin/bash
set -e

PROJECT=nianien
REGION=asia-east1
REPO=litebook
IMAGE=litebook-app
TAG=latest
FULL_IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/${IMAGE}:${TAG}"

# 从 .env 读取环境变量
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

echo "🔨 远程构建: ${FULL_IMAGE}"
gcloud builds submit --tag "${FULL_IMAGE}" --project "${PROJECT}" .

echo "🚀 部署到 Cloud Run..."
gcloud run deploy litebook \
  --image "${FULL_IMAGE}" \
  --project "${PROJECT}" \
  --platform managed \
  --region "${REGION}" \
  --allow-unauthenticated \
  --set-env-vars="DB_URL=${DB_URL},SECRET_KEY=${SECRET_KEY}"

URL=$(gcloud run services describe litebook --project "${PROJECT}" --region "${REGION}" --format="value(status.url)")
echo "✅ 部署完成: ${URL}"
