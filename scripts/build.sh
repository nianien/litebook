#远程构建
gcloud builds submit \
  --tag asia-east1-docker.pkg.dev/nianien/liteblog/liteblog-app:latest .

gcloud run deploy liteblog \
  --image asia-east1-docker.pkg.dev/nianien/liteblog/liteblog-app:latest \
  --platform managed \
  --region asia-east1 \
  --allow-unauthenticated