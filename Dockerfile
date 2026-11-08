FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    LANG=C.UTF-8 \
    TZ=Asia/Shanghai \
    PORT=8788

WORKDIR /app

COPY . /app

RUN pip install --no-cache-dir packaging tzdata

EXPOSE 8788

CMD ["python", "wb_proxy.py", "--host", "0.0.0.0", "--lan"]