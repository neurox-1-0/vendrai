FROM postgres:16.13-bookworm

RUN apt-get update \
    && apt-get install --yes --no-install-recommends pgbackrest \
    && rm -rf /var/lib/apt/lists/*

COPY infra/postgres/pgbackrest.conf /etc/pgbackrest/pgbackrest.conf
COPY infra/postgres/neurox-backup /usr/local/bin/neurox-backup
RUN chmod 0755 /usr/local/bin/neurox-backup \
    && mkdir -p /var/spool/pgbackrest \
    && chown -R postgres:postgres /var/spool/pgbackrest
