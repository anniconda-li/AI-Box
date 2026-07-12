# wkt-ai-server 部署配置

本仓库是独立的 AI 后端仓库。以下配置用于本地和测试环境验证，本次规范化不执行生产部署，也不合并对讲服务或 OTA 服务。

## 固定身份

| 配置项 | 值 |
| --- | --- |
| 项目与 GitHub 仓库 | `wkt-ai-server` |
| Docker 镜像 | `wkt-ai-server` |
| Compose 服务 | `ai` |
| 容器 | `wkt-ai-server` |
| HTTP 端口 | `8000` |

`wkt-platform` 只是本地父目录，不初始化 Git，不作为 Compose 工程或 monorepo。`walkie-talkiev1` 固件项目不属于本仓库。

## 本地镜像验证

在仓库根目录准备 `.env` 后执行：

```powershell
docker build -t wkt-ai-server:local .
docker run --rm --name wkt-ai-server --env-file .env -p 8000:8000 wkt-ai-server:local
```

另一个终端执行健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

## Compose 验证

```powershell
docker compose up --build ai
```

`compose.yaml` 只定义 `ai` 服务，并将本地 `uploads`、`outputs` 目录挂载到容器。API 路径、端口、协议和请求响应格式仍由现有应用代码定义。

## GitHub Actions

`.github/workflows/ci.yml` 在 push 和 pull request 时运行离线冒烟测试并构建 `wkt-ai-server:<commit-sha>` 镜像。工作流不推送镜像、不启动远程容器，也不部署任何生产环境。

生产环境的镜像仓库地址、凭据、主机、反向代理、TLS、持久卷和密钥管理当前均未配置，需要由实际部署环境单独提供。
