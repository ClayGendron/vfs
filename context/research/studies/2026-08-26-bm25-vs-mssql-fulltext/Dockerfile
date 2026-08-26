# SQL Server 2022 with Full-Text Search — the stock image ships without
# it and without the Microsoft apt repository that carries it. Spike-only;
# the test compose file stays on the stock image.
#   docker build --platform linux/amd64 -t vfs-mssql-fts .
#   docker run --platform linux/amd64 -d --name vfs-mssql-fts -p 14331:1433 \
#     -e ACCEPT_EULA=Y -e MSSQL_SA_PASSWORD=vfsStr0ngPassw0rd -e MSSQL_PID=Developer vfs-mssql-fts
FROM mcr.microsoft.com/mssql/server:2022-latest
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gnupg ca-certificates \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft.gpg] https://packages.microsoft.com/ubuntu/22.04/mssql-server-2022 jammy main" \
       > /etc/apt/sources.list.d/mssql-server-2022.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends mssql-server-fts \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
USER mssql
