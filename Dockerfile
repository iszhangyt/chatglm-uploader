FROM python:3.9-slim

WORKDIR /app

# 拷贝依赖文件并安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝应用代码
COPY . .

# 创建数据目录
RUN mkdir -p /app/data

# 指定端口
EXPOSE 5500

# 设置启动命令 - 使用gunicorn代替Flask开发服务器
CMD ["gunicorn", "--bind", "0.0.0.0:5500", "--workers", "2", "--threads", "4", "app:app"] 