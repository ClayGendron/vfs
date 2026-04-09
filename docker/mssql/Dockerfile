FROM --platform=linux/amd64 ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    ACCEPT_EULA=Y \
    MSSQL_PID=Developer \
    PATH="/opt/mssql-tools18/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl gnupg ca-certificates lsb-release apt-transport-https \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
         | gpg --dearmor -o /etc/apt/trusted.gpg.d/microsoft.gpg \
    && curl -fsSL https://packages.microsoft.com/config/ubuntu/22.04/mssql-server-2025.list \
         -o /etc/apt/sources.list.d/mssql-server-2025.list \
    && curl -fsSL https://packages.microsoft.com/config/ubuntu/22.04/prod.list \
         -o /etc/apt/sources.list.d/mssql-prod.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        mssql-server \
        mssql-server-fts \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
        mssql-tools18 \
        unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
COPY init-db.sql /usr/local/share/init-db.sql
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 1433
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["/opt/mssql/bin/sqlservr"]
