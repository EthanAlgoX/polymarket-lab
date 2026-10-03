# 经过登录保护的服务器部署

[English](README.md) · [简体中文](README_CN.md)

将应用部署在 `/polymarket-lab/`，与同一域名下的其他网站共存。需要 Linux、
Docker Engine、Docker Compose ≥2.24、HTTPS Nginx 和已有登录保护。保持一个应用
进程；服务在本地电脑关机后继续采集公开数据，源接口异常会正常展示。

## 安装与启动

审阅后的代码放到 `/opt/polymarket-lab/app`。不要随代码上传本地 `.env`、API
密钥、数据库、日志、翻译缓存或 macOS 虚拟环境。

```sh
sudo install -d -m 700 -o 10001 -g 10001 /opt/polymarket-lab/data /opt/polymarket-lab/logs
cd /opt/polymarket-lab/app/deploy
cp .env.example .env
chmod 600 .env
sudo docker compose -p polymarket-lab build
sudo docker compose -p polymarket-lab up -d
sudo docker compose -p polymarket-lab ps
curl --fail http://127.0.0.1:8011/health
```

启动前在 `.env` 设置 `PMS_CONFIGURATION_ORIGIN` 为准确的 HTTPS 来源，确认
8011 未被占用。`PMS_ROOT_PATH=/polymarket-lab` 用于页面、静态资源、API、导出、
市场详情链接和 Swagger。服务器 Compose 使用 Linux host 网络，应用仅监听
`127.0.0.1:8011`。本地桌面 Docker 仍使用根目录的 `docker-compose.yml`。

镜像使用 `10001:10001` 非 root 身份。数据库、翻译缓存、API 配置和日志持久化
在独立的宿主机目录。容器标准输出有轮转；应用日志单独管理。Docker 健康检查
只报告状态；`restart: unless-stopped` 能重启退出的进程，不会重启仍在运行但
不健康的容器。网站健康不等于行情新鲜。

## Nginx 与中文 API 配置

参考 [Nginx 示例](nginx-subpath.conf.example)，替换域名和登录文件路径，加入
已有 HTTPS server。必须用登录保护覆盖**整个路径**，包括 API、翻译、配置、
导出和静态文件。应用没有独立用户系统：获得访问权限的用户共享扫描参数、
观察记录及服务端翻译配置。不要因行情是公开数据而移除登录保护。

Nginx 去掉请求路径的 `/polymarket-lab/` 前缀，覆盖代理协议及客户端地址，
不向应用传递登录密码。应用只信任来自 loopback 的代理头。先 `nginx -t`，
再 reload；保留同域名下其他站点、证书和既有认证配置。

`PMS_CONFIGURATION_ORIGIN` 明确开启服务器上的 API 配置入口；它是来源检查，
**不能代替身份认证**。留空时只允许本机修改密钥。远程保存/移除必须来自指定的
HTTPS 同源页面。登录后进入 **Settings → Translation API** 配置自己的 LLM，再
选择 **中文**。英文无需密钥。本地电脑密钥不会自动复制。网站保存立即生效，
不做付费连接测试；密钥保存在仅所有者可读写的 `data/llm-config.json`，不会返回浏览器。

## 验收、更新与回滚

未登录的页面和 API 应返回 401。登录后验证七个页面、静态资源、健康、系统
状态、目录、API 配置、Swagger 和 CSV 导出都在子路径下工作，再检查类别筛选、
市场详情、手机菜单及未配置 API 的中文提示。可提交不合法的配置体核验访问与
校验，不保存密钥或消耗翻译额度。同时复核原有其他站点。

更新前构建带版本的镜像，保留 `deploy/.env`、数据和日志，备份当前镜像引用与
Nginx 配置。SQLite 用 `sqlite3.Connection.backup` 建一致性快照；配置备份可能
含密钥，须私密保存。代码回滚只退镜像和代理配置，保留最新数据；不要覆盖已有
观察记录。发布返回未知结果时，先读服务器上的持久化回执，再决定是否继续。
