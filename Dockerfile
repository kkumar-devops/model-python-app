FROM prefecthq/prefect:2.14-python3.11

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install dlt and dependencies
# Copy requirements first for better layer caching
COPY requirements.txt* ./

# Install Python dependencies
RUN if [ -f requirements.txt ]; then \
        pip install --no-cache-dir -r requirements.txt; \
    else \
        pip install --no-cache-dir \
            dlt[filesystem]>=0.4.0 \
            dlt[postgres]>=0.4.0 \
            sqlalchemy>=2.0.0 \
            psycopg2-binary>=2.9.0 \
            s3fs>=2023.10.0; \
    fi

WORKDIR /prefect

# Copy flows directory
COPY flows/ /prefect/flows/

# Start Prefect worker
# Note: Flow Server removed - manual triggers now use Prefect API
CMD ["prefect", "worker", "start", "--pool", "default", "--type", "process"]

