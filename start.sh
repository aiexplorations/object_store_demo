#!/bin/bash

# Add error handling
set -e  # Exit on error

echo "Initializing Object Store deployment..."

# Initialize Docker Swarm if not already in swarm mode
if ! docker info | grep -q "Swarm: active"; then
    echo "Initializing Docker Swarm..."
    docker swarm init --advertise-addr 127.0.0.1
else
    echo "Swarm mode already active"
fi

# Start local registry if not running
if ! docker ps | grep -q "registry:2"; then
    echo "Starting local registry..."
    docker run -d -p 5000:5000 --restart=always --name registry registry:2
    sleep 5
fi

# Clean up any existing stack first
if docker stack ls | grep -q "objectstore"; then
    echo "Removing existing stack..."
    docker stack rm objectstore
    sleep 20  # Wait for cleanup
fi

# Build and push images
echo "Building images..."
docker compose build

PROJECT_NAME=$(basename $(pwd))
echo "Tagging images..."
docker tag ${PROJECT_NAME}-object-receiver:latest localhost:5000/object-receiver:latest
docker tag ${PROJECT_NAME}-object-getter:latest localhost:5000/object-getter:latest
docker tag ${PROJECT_NAME}-orchestrator:latest localhost:5000/orchestrator:latest

echo "Pushing images to local registry..."
docker push localhost:5000/object-receiver:latest
docker push localhost:5000/object-getter:latest
docker push localhost:5000/orchestrator:latest

# Deploy stack
echo "Deploying stack..."
docker stack deploy -c docker-compose.yml objectstore

# Improved service check function
check_services() {
    local retries=0
    local max_retries=30

    echo "Waiting for services to initialize..."
    sleep 30  # Initial wait for services to start deploying

    while [ $retries -lt $max_retries ]; do
        echo "Checking service status (attempt $((retries + 1))/$max_retries)..."
        
        # Get service status
        local services_status=$(docker service ls --format "{{.Name}},{{.Replicas}}")
        local failed_services=()
        
        while IFS=',' read -r name replicas; do
            if [[ $name == objectstore_* ]]; then
                local running=$(echo $replicas | cut -d'/' -f1)
                local desired=$(echo $replicas | cut -d'/' -f2)
                
                if [ "$running" != "$desired" ]; then
                    failed_services+=("$name: $running/$desired")
                    echo "Service $name not ready"
                fi
            fi
        done <<< "$services_status"
        
        if [ ${#failed_services[@]} -eq 0 ]; then
            echo "All services are running!"
            return 0
        fi
        
        echo "Waiting for services to stabilize..."
        sleep 10
        retries=$((retries + 1))
    done
    
    return 1
}

# Update the MinIO health check function
check_minio_health() {
    echo "Checking MinIO health..."
    local retries=0
    local max_retries=15
    
    while [ $retries -lt $max_retries ]; do
        if curl -sf http://localhost:9000/minio/health/live > /dev/null; then
            echo "MinIO is healthy!"
            return 0
        fi
        echo "Waiting for MinIO to be ready..."
        sleep 5
        retries=$((retries + 1))
    done
    
    echo "ERROR: MinIO failed to become healthy"
    docker service logs objectstore_minio1
    return 1
}

# Wait for services to be ready
if check_services; then
    if check_minio_health; then
        echo "Deployment complete! All services are running and healthy."
        echo "Monitor logs with: docker service logs -f objectstore_orchestrator"
    else
        echo "Error: MinIO cluster is not healthy. Check logs for details."
        docker service logs objectstore_minio1
        docker service logs objectstore_minio2
        exit 1
    fi
else
    echo "Error: Some services failed to start. Check logs for details."
    docker service ls
    exit 1
fi
