FROM python:3.13-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.lock requirements-postgres.txt requirements.txt ./
RUN pip install --no-cache-dir -r requirements.lock -r requirements-postgres.txt \
    && groupadd --gid 10001 xcomify \
    && useradd --uid 10001 --gid 10001 --create-home xcomify
COPY --chown=10001:10001 . /app
RUN mkdir -p /app/.data && chown 10001:10001 /app/.data
USER 10001:10001
EXPOSE 8080
CMD ["python", "run.py", "--no-browser"]
