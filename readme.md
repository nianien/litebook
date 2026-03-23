# LiteBook

一个轻量级博客平台，支持文章发布、分类管理、评论互动、点赞等功能。

**技术栈**: Python 3.12 / FastAPI / SQLAlchemy / Jinja2 / Quill.js / PostgreSQL / Docker / Google Cloud Run

**主要功能**:
- 富文本文章编辑（Quill.js）与分类管理
- 评论系统（支持嵌套回复和匿名评论）
- 点赞、浏览量统计
- JWT 用户认证

---

## 目录

- [本地开发](#本地开发)
- [部署到 Google Cloud Run](#部署到-google-cloud-run)
- [常用运维命令](#常用运维命令)
- [故障排查](#故障排查)

---

## 本地开发

### 前置条件

- Python 3.12+
- 一个 PostgreSQL 数据库（推荐使用 [Neon](https://neon.tech) 免费版，注册后一分钟即可获得连接串）

### 第 1 步：准备数据库

如果使用 Neon：
1. 注册 https://neon.tech 并创建项目
2. 在 Dashboard 的 **Connection Details** 中复制连接串，格式如：
   ```
   postgresql://user:password@ep-xxx.region.aws.neon.tech/dbname?sslmode=require
   ```

如果使用本地 PostgreSQL：
```
postgresql://postgres:yourpassword@localhost:5432/litebook
```

### 第 2 步：配置环境变量

在项目根目录创建 `.env` 文件：

```env
DB_URL=postgresql://user:password@host/dbname?sslmode=require
SECRET_KEY=替换为一个随机字符串
```

> `SECRET_KEY` 用于 JWT 签名，可以用 `python -c "import secrets; print(secrets.token_urlsafe(32))"` 生成。

### 第 3 步：安装依赖并启动

```shell
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

访问 http://localhost:8000 确认页面正常。

### Docker 本地运行（可选）

```shell
docker build -t litebook-app:latest .
docker rm -f litebook-app 2>/dev/null
docker run -d --name litebook-app -p 8000:8080 --env-file .env litebook-app:latest

# 确认启动成功
docker logs --tail 20 litebook-app
```

访问 http://localhost:8000 确认。

---

## 部署到 Google Cloud Run

以下是从零开始的完整流程。如果你的 GCP 环境已经初始化过，可以直接跳到 [第 5 步：部署](#第-5-步部署)。

### 需要替换的配置

文档中以下值需要替换为你自己的：

| 占位符 | 含义 | 示例 |
|--------|------|------|
| `PROJECT_ID` | GCP 项目 ID | `nianien` |
| `REGION` | 部署区域 | `asia-east1` |
| `BILLING_ACCOUNT` | 结算账号 ID | `01D488-A4C3C6-D364A1` |

> 下面的命令使用本项目的实际值，fork 后请替换。

### 前置条件

- 安装 [Google Cloud CLI](https://cloud.google.com/sdk/docs/install)
- 拥有 GCP 账号

### 第 1 步：初始化 GCP 项目

```shell
# 登录
gcloud auth login

# 设置默认项目
gcloud config set project nianien

# 绑定结算账号（没有结算账号则无法使用 Cloud Build 和 Cloud Run）
gcloud beta billing projects link nianien \
  --billing-account=01D488-A4C3C6-D364A1
```

验证：`gcloud config get-value project` 应输出 `nianien`。

### 第 2 步：启用所需 API

Cloud Run 部署依赖三个服务：

| API | 用途 |
|-----|------|
| `cloudbuild.googleapis.com` | 远程构建 Docker 镜像 |
| `artifactregistry.googleapis.com` | 存储 Docker 镜像 |
| `run.googleapis.com` | 运行容器服务 |

```shell
gcloud services enable \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  artifactregistry.googleapis.com
```

### 第 3 步：创建 Artifact Registry 仓库

Artifact Registry 是 GCP 的容器镜像仓库，类似 Docker Hub：

```shell
gcloud artifacts repositories create litebook \
  --repository-format=docker \
  --location=asia-east1 \
  --description="LiteBook blog platform"
```

验证：`gcloud artifacts repositories list --location=asia-east1` 应显示 `litebook`。

### 第 4 步：配置 IAM 权限

Cloud Build 使用服务账号执行构建和部署，需要授予相应权限：

```shell
# 获取项目编号（自动生成的数字 ID，不同于项目 ID）
PROJECT_NUMBER=$(gcloud projects describe nianien --format="value(projectNumber)")
```

授予三个角色：

```shell
# 1) 允许 Cloud Build 推送镜像到 Artifact Registry
gcloud projects add-iam-policy-binding nianien \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

# 2) 允许 Cloud Build 部署 Cloud Run 服务
gcloud projects add-iam-policy-binding nianien \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/run.admin"

# 3) 允许 Cloud Build 以 Compute 默认服务账号身份部署（Cloud Run 要求）
gcloud iam service-accounts add-iam-policy-binding \
  ${PROJECT_NUMBER}-compute@developer.gserviceaccount.com \
  --member="serviceAccount:${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"
```

> **为什么需要三个角色？** Cloud Build 构建完镜像后需要推送（第 1 个），然后部署到 Cloud Run（第 2 个），部署时需要绑定运行时服务账号（第 3 个）。缺少任何一个都会导致权限报错。

### 第 5 步：部署

确保 `.env` 文件已配置好 `DB_URL` 和 `SECRET_KEY`，然后执行：

```shell
bash scripts/deploy.sh
```

脚本执行流程：
1. 读取 `.env` 中的环境变量
2. 远程构建 Docker 镜像并推送到 Artifact Registry
3. 部署到 Cloud Run 并注入环境变量
4. 打印服务访问地址

部署成功后会输出类似：
```
✅ 部署完成: https://litebook-xxxx-xx.a.run.app
```

访问该地址确认服务正常。

---

## 项目结构

```
GCP Project
├── Artifact Registry        # 镜像仓库
│   └── litebook/litebook-app:latest
├── Cloud Build              # 远程构建 Docker 镜像
└── Cloud Run: litebook      # 运行容器，对外提供 HTTPS 服务
```

镜像路径格式：`[REGION]-docker.pkg.dev/[PROJECT_ID]/[REPO]/[IMAGE]:[TAG]`

---

## 常用运维命令

```shell
# 查看服务状态和访问地址
gcloud run services describe litebook --region asia-east1

# 查看最近日志
gcloud run services logs read litebook --region asia-east1 --limit 50

# 查看历史部署版本
gcloud run revisions list --service litebook --region asia-east1

# 回滚到上一个版本
gcloud run services update-traffic litebook --region asia-east1 --to-revisions=REVISION_NAME=100
```

---

## 故障排查

### 镜像推送失败：`Permission 'artifactregistry.repositories.uploadArtifacts' denied`

可能的原因：

1. **Artifact Registry 仓库不存在**：确认仓库已创建，执行 `gcloud artifacts repositories list --location=asia-east1 --project=PROJECT_ID` 检查。
2. **gcloud 默认项目与目标项目不一致**：`gcloud builds submit` 默认使用当前项目，如果本地 `gcloud config get-value project` 不是目标项目，构建会在错误的项目下执行。`deploy.sh` 已通过 `--project` 参数解决此问题。
3. **Cloud Build 服务账号缺少权限**：执行[第 4 步](#第-4-步配置-iam-权限)中的第 1 条命令。

### 部署失败：`Could not create or update Cloud Run service`

Cloud Build 服务账号缺少 Cloud Run 部署权限。执行[第 4 步](#第-4-步配置-iam-权限)中的第 2、3 条命令。

### 服务启动后立即崩溃（日志中 `connection refused` 或 `password authentication failed`）

`DB_URL` 配置错误。检查：
- `.env` 中的连接串是否正确
- Neon 数据库是否处于 Active 状态（免费版会自动休眠）
- 部署时是否传入了环境变量（`deploy.sh` 会自动处理）

### 本地 Docker 构建慢

首次构建需要下载基础镜像和安装依赖，后续构建会利用 Docker 缓存。确保 `.dockerignore` 排除了 `.venv/` 等大目录。

### `gcloud` 命令提示 `billing account is not enabled`

项目未绑定结算账号。执行[第 1 步](#第-1-步初始化-gcp-项目)中的绑定命令。

### 多项目环境下操作了错误的项目

如果本地 `gcloud` 配置的默认项目不是部署目标项目，所有不带 `--project` 的命令都会作用到错误的项目上（例如在 A 项目下创建了仓库，却往 B 项目推送镜像）。

排查方法：
```shell
# 查看当前默认项目
gcloud config get-value project

# 临时切换（影响后续所有命令）
gcloud config set project nianien

# 或在单条命令中指定（不影响全局配置）
gcloud artifacts repositories list --project=nianien --location=asia-east1
```

> `deploy.sh` 中所有 gcloud 命令均已显式指定 `--project`，不受本地默认项目影响。

### 清理多余的 Artifact Registry 仓库

如果在错误的项目下创建了仓库，或需要清理旧仓库：

```shell
# 列出仓库
gcloud artifacts repositories list --location=asia-east1 --project=PROJECT_ID

# 删除仓库（会删除其中所有镜像，不可恢复）
gcloud artifacts repositories delete REPO_NAME --location=asia-east1 --project=PROJECT_ID --quiet
```
