# ChatGLM图床

一个基于ChatGLM文件上传API的简单图床应用，支持京东图床。

## 功能
- 支持ChatGLM和京东双渠道上传图片
- 获取图片URL并显示
- 一键复制图片链接
- 查看和管理上传历史
- 图片渠道选择和记忆功能
- 用户验证功能

## 使用方法

### 直接运行
1. 安装依赖：`pip install -r requirements.txt`
2. 启动服务器：`python app.py`
   注意：这种方式使用的是Flask开发服务器，仅适合开发和测试环境
3. 访问 http://localhost:5500 使用图床
4. 使用默认验证码 `admin123` 进行验证

### 生产环境运行
1. 安装依赖：`pip install -r requirements.txt`
2. 使用Gunicorn启动服务：
   ```bash
   gunicorn --bind 0.0.0.0:5500 --workers 2 --threads 4 app:app
   ```
3. 访问 http://localhost:5500 使用图床
4. 使用默认验证码 `admin123` 进行验证

### Docker部署

#### 前提条件
- 安装Docker和Docker Compose
  - Docker安装：[https://docs.docker.com/get-docker/](https://docs.docker.com/get-docker/)
  - Docker Compose安装：[https://docs.docker.com/compose/install/](https://docs.docker.com/compose/install/)

#### 快速启动
1. 克隆代码库到本地
```bash
git clone https://github.com/iszhangyt/chatglm-uploader.git
cd chatglm-uploader
```

2. 使用Docker Compose构建并启动服务
```bash
docker compose up -d
```

3. 访问应用
   - 打开浏览器，访问 `http://localhost:5500` 即可使用应用
   - 使用默认验证码 `admin123` 进行验证

#### 数据持久化
所有上传历史和验证配置都存储在 `./data` 目录中，该目录通过 Docker 卷挂载到容器内。
您可以备份此目录以保存数据。

#### 常用Docker操作

##### 查看日志
```bash
docker compose logs -f
```

##### 重启服务
```bash
docker compose restart
```

##### 停止服务
```bash
docker compose down
```

##### 重新构建镜像
如果您修改了代码，需要重新构建镜像：
```bash
docker compose build
docker compose up -d
```

#### Docker配置说明
您可以在docker-compose.yml文件中修改以下配置：
- 端口映射：修改 `"5500:5500"` 的第一个数字可以更改主机端口
- 时区设置：修改 `TZ=Asia/Shanghai` 可以更改容器时区

#### Docker部署疑难解答
1. 如果遇到权限问题，尝试为数据目录添加适当的权限：
```bash
chmod -R 777 ./data
```

2. 如果容器无法启动，请检查日志：
```bash
docker compose logs
```

## 技术栈
- 后端：Flask (Python)
- 前端：HTML, CSS, JavaScript
- 容器化：Docker, Docker Compose

## 数据存储
所有上传历史和配置信息都存储在 `data` 目录中，包括：
- `history.json`：上传历史记录
- `verification.json`：验证配置信息 