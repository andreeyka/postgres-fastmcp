FROM postgres:16

# Install hypopg extension for PostgreSQL 16
RUN apt-get update && \
    apt-get install -y postgresql-16-hypopg && \
    rm -rf /var/lib/apt/lists/*
