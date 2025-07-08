
# gcp中Project与Repo、Image的关系
```text
#GCP Project（nianien）
 #│
 #├── Artifact Registry
 #│   ├── Repository: my-fastapi (Docker)
 #│   │   ├── Image: fastapi-app:latest
 #│   │   └── Image: fastapi-app:v1
 #│   └── Repository: my-python (Python 包)
 #│
 #├── Cloud Run 服务
 #├── Cloud Build 任务
 #└── IAM 权限设置

```
# GCP Artifact Registry Docker Image Path
[LOCATION]-docker.pkg.dev/[PROJECT-ID]/[REPOSITORY]/[IMAGE]

# 用命令行添加角色 Editor 或 Cloud Build Editor：
```shell
gcloud projects add-iam-policy-binding nianien \
  --member="user:nianien@gmail.com" \
  --role="roles/cloudbuild.builds.editor" 
```

# 设置当前project
```shell
gcloud config set project nianien
```

# 绑定账单账户
```shell
gcloud beta billing projects link nianien \
  --billing-account=01D488-A4C3C6-D364A1
```

# 创建 Artifact Registry 仓库
```shell
gcloud artifacts repositories create liteblog \
  --repository-format=docker \
  --location=asia-east1 \
  --description="lite blog by FastAPI"
```


# 配置权限
```shell
gcloud auth configure-docker asia-east1-docker.pkg.dev
```
# 本地构建
```shell
# 构建镜像
#确保登录并设置Docker认证
gcloud auth login
gcloud auth configure-docker asia-east1-docker.pkg.dev
# 推送镜像到Artifact Registry
docker buildx build \
  --platform linux/amd64 \
  -t asia-east1-docker.pkg.dev/nianien/liteblog/liteblog-app:latest \
  --push .
```

# 远程构建(建议)
```shell
gcloud builds submit \
  --tag asia-east1-docker.pkg.dev/nianien/liteblog/liteblog-app:latest .
```

# 部署启动
```shell
gcloud run deploy liteblog \
  --image asia-east1-docker.pkg.dev/nianien/liteblog/liteblog-app:latest \
  --platform managed \
  --region asia-east1 \
  --allow-unauthenticated
```

# 本地docker启动
```shell
# 构建镜像
docker build -t liteblog:latest .
# 删除旧容器
docker rm -f liteblog_app
# 运行容器
docker run -d --name liteblog_app -p 8000:8080 --env-file .env liteblog:latest

# 查看日志
docker logs --tail 50 liteblog_app
```

# 本地服务器启动
```shell
GOOGLE_APPLICATION_CREDENTIALS="/Users/skyfalling/Workspace/cloud/liteblog/credentials.json" uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```