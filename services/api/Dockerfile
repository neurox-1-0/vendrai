# syntax=docker/dockerfile:1.7
FROM python:3.12.13-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/api
RUN addgroup --system neurox && adduser --system --ingroup neurox neurox
COPY services/api/requirements.txt ./requirements.txt
# The cache mount keeps wheels between builds without adding them to the image
# layer, so a dependency bump re-downloads only what changed.
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install --retries 5 --timeout 60 --requirement requirements.txt
COPY services/api ./
RUN chown -R neurox:neurox /srv/api
USER neurox
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
