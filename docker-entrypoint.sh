#!/bin/bash

# Docker entrypoint script for postgres-mcp
# Handles localhost replacement in connection strings and config.json

set -euo pipefail

# Function to replace localhost in a string with the Docker host
replace_localhost() {
    local input_str="$1"
    local docker_host=""

    # Try to determine Docker host address
    if ping -c 1 -w 1 host.docker.internal >/dev/null 2>&1; then
        docker_host="host.docker.internal"
        echo "Docker Desktop detected: Using host.docker.internal for localhost" >&2
    elif ping -c 1 -w 1 172.17.0.1 >/dev/null 2>&1; then
        docker_host="172.17.0.1"
        echo "Docker on Linux detected: Using 172.17.0.1 for localhost" >&2
    else
        echo "WARNING: Cannot determine Docker host IP. Using original address." >&2
        return 1
    fi

    # Replace localhost with Docker host
    if [[ -n "$docker_host" ]]; then
        local new_str="${input_str/localhost/$docker_host}"
        echo "  Remapping: $input_str --> $new_str" >&2
        echo "$new_str"
        return 0
    fi

    # No replacement made
    echo "$input_str"
    return 1
}

# Process config.json if it exists and contains localhost
CONFIG_FILE="${CONFIG_FILE:-/app/config.json}"
if [[ -f "$CONFIG_FILE" ]]; then
    if grep -q "localhost" "$CONFIG_FILE" 2>/dev/null; then
        echo "Found localhost in config.json, processing..." >&2
        docker_host=""
        
        # Determine Docker host
        if ping -c 1 -w 1 host.docker.internal >/dev/null 2>&1; then
            docker_host="host.docker.internal"
        elif ping -c 1 -w 1 172.17.0.1 >/dev/null 2>&1; then
            docker_host="172.17.0.1"
        fi
        
        if [[ -n "$docker_host" ]]; then
            # Check if file is writable
            if [[ -w "$CONFIG_FILE" ]]; then
                # Use sed to replace localhost in config.json (only in database_uri fields)
                # This preserves JSON structure
                sed -i.bak "s|postgresql://\([^:]*\):\([^@]*\)@localhost|postgresql://\1:\2@${docker_host}|g" "$CONFIG_FILE"
                sed -i.bak "s|postgres://\([^:]*\):\([^@]*\)@localhost|postgres://\1:\2@${docker_host}|g" "$CONFIG_FILE"
                rm -f "${CONFIG_FILE}.bak"
                echo "Updated config.json: replaced localhost with ${docker_host}" >&2
            else
                # File is read-only (e.g., mounted volume), create a writable copy in working directory
                # Application looks for config.json in current working directory (/app)
                WORKING_CONFIG="/app/config.json"
                cp "$CONFIG_FILE" "$WORKING_CONFIG"
                sed -i "s|postgresql://\([^:]*\):\([^@]*\)@localhost|postgresql://\1:\2@${docker_host}|g" "$WORKING_CONFIG"
                sed -i "s|postgres://\([^:]*\):\([^@]*\)@localhost|postgres://\1:\2@${docker_host}|g" "$WORKING_CONFIG"
                echo "Created writable config.json with localhost replaced: ${docker_host}" >&2
                echo "Using: $WORKING_CONFIG" >&2
            fi
        fi
    fi
fi

# Check and replace localhost in DATABASE_URI environment variable if it exists
if [[ -n "${DATABASE_URI:-}" && "$DATABASE_URI" == *"postgres"*"://"*"localhost"* ]]; then
    echo "Found localhost in DATABASE_URI: $DATABASE_URI" >&2
    new_uri=$(replace_localhost "$DATABASE_URI")
    if [[ $? -eq 0 ]]; then
        export DATABASE_URI="$new_uri"
    fi
fi

# Process command-line arguments for postgres:// or postgresql:// URLs that contain localhost
processed_args=()
processed_args+=("$1")
shift 1

for arg in "$@"; do
    if [[ "$arg" == *"postgres"*"://"*"localhost"* ]]; then
        echo "Found localhost in database connection: $arg" >&2
        new_arg=$(replace_localhost "$arg")
        if [[ $? -eq 0 ]]; then
            processed_args+=("$new_arg")
        else
            processed_args+=("$arg")
        fi
    else
        processed_args+=("$arg")
    fi
done

# Ensure host is set to 0.0.0.0 for HTTP transport when running in Docker
# This allows the server to be accessible from outside the container
if [[ " ${processed_args[@]} " =~ " --transport http " ]] || \
   [[ " ${processed_args[@]} " =~ " --transport=http " ]] || \
   [[ ! " ${processed_args[@]} " =~ " --transport " ]]; then
    # HTTP transport is default or explicitly set
    if [[ ! " ${processed_args[@]} " =~ " --host " ]] && \
       [[ ! " ${processed_args[@]} " =~ " --host=" ]]; then
        echo "HTTP transport detected, adding --host=0.0.0.0 for Docker" >&2
        processed_args+=("--host=0.0.0.0")
    fi
fi

echo "----------------" >&2
echo "Executing command:" >&2
echo "${processed_args[@]}" >&2
echo "----------------" >&2

# Execute the command with the processed arguments
exec "${processed_args[@]}"
