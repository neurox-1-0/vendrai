# syntax=docker/dockerfile:1.7
FROM python:3.12.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/risk
RUN addgroup --system neurox && adduser --system --ingroup neurox neurox
COPY services/mock_risk/requirements.txt ./
RUN --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    pip install --retries 5 --timeout 60 --requirement requirements.txt
COPY services/mock_risk/app.py ./
RUN chown -R neurox:neurox /srv/risk
USER neurox
EXPOSE 8095
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8095"]
