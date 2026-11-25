# PostgreSQL 17 Sandbox with HypoPG extension
FROM postgres:17-bookworm

LABEL maintainer="Sanidhya Vijay <sanidhyavijay2004@gmail.com>"
LABEL description="SQL Doctor Throwaway PostgreSQL 17 sandbox container with HypoPG"

# Install postgresql-17-hypopg from Debian / PGDG repository
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-17-hypopg \
    && rm -rf /var/lib/apt/lists/*

# Add extension initialization script to auto-create hypopg on default database
RUN echo "CREATE EXTENSION IF NOT EXISTS hypopg;" > /docker-entrypoint-initdb.d/01_hypopg.sql

EXPOSE 5432
