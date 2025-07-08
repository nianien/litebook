gcloud config set project nianien

gcloud beta billing projects link nianien \
  --billing-account=01D488-A4C3C6-D364A1

# 创建 Artifact Registry 仓库
gcloud artifacts repositories create liteblog \
  --repository-format=docker \
  --location=asia-east1 \
  --description="lite blog by FastAPI"

#本地构建
#docker build -t asia-east1-docker.pkg.dev/nianien/liteblog/liteblog-app:latest .
#docker build -t asia-east1-docker.pkg.dev/nianien/liteblog/liteblog-app:latest .

#远程构建
gcloud builds submit \
  --tag asia-east1-docker.pkg.dev/nianien/liteblog/liteblog-app:latest .

gcloud run deploy liteblog \
  --image asia-east1-docker.pkg.dev/nianien/liteblog/liteblog-app:latest \
  --platform managed \
  --region asia-east1 \
  --allow-unauthenticated \
  --memory 512Mi \
  --cpu 1 \
  --port 8080 \
  --max-instances 10