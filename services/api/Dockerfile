FROM python:3.12.4-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv/api
RUN addgroup --system neurox && adduser --system --ingroup neurox neurox
COPY services/api/requirements.txt ./requirements.txt
RUN pip install --requirement requirements.txt
COPY services/api ./
RUN chown -R neurox:neurox /srv/api
USER neurox
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

