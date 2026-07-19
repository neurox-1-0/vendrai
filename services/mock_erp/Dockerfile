FROM python:3.12.4-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv/erp
RUN addgroup --system neurox && adduser --system --ingroup neurox neurox
COPY services/mock_erp/requirements.txt ./
RUN pip install --requirement requirements.txt
COPY services/mock_erp/app.py ./
RUN chown -R neurox:neurox /srv/erp
USER neurox
EXPOSE 8090
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8090"]

