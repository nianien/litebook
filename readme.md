
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

#用命令行添加角色 Editor 或 Cloud Build Editor：
```shell
gcloud projects add-iam-policy-binding nianien \
  --member="user:nianien@gmail.com" \
  --role="roles/cloudbuild.builds.editor" 
```
# GCP Artifact Registry Docker Image Path
[LOCATION]-docker.pkg.dev/[PROJECT-ID]/[REPOSITORY]/[IMAGE]


# FastAPI Blog

## 运行

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

访问: http://127.0.0.1:8000

- 注册/登录
- 发布/浏览/编辑/删除文章
- 记录浏览历史