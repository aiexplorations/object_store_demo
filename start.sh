#!/bin/bash

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
    # Wait for registry to be ready
    sleep 5
fi

# Build images
echo "Building images..."
docker compose build

# Get the project name (directory name by default)
PROJECT_NAME=$(basename $(pwd))

# Tag images for local registry using project name
echo "Tagging images..."
docker tag ${PROJECT_NAME}-object-receiver:latest localhost:5000/object-receiver:latest
docker tag ${PROJECT_NAME}-object-getter:latest localhost:5000/object-getter:latest
docker tag ${PROJECT_NAME}-orchestrator:latest localhost:5000/orchestrator:latest

# Push images to local registry
echo "Pushing images to local registry..."
docker push localhost:5000/object-receiver:latest
docker push localhost:5000/object-getter:latest
docker push localhost:5000/orchestrator:latest

# Deploy stack
echo "Deploying stack..."
docker stack deploy -c docker-compose.yml objectstore

# Function to check if all services are running
check_services() {
    local retries=0
    local max_retries=30

    while [ $retries -lt $max_retries ]; do
        echo "Checking service status (attempt $((retries + 1))/$max_retries)..."
        
        # Get all services and their desired/running replicas
        local services=$(docker service ls --format "{{.Name}} {{.Replicas}}")
        local all_running=true
        
        while read -r service; do
            local name=$(echo $service | cut -d' ' -f1)
            local replicas=$(echo $service | cut -d' ' -f2)
            local running=$(echo $replicas | cut -d'/' -f1)
            local desired=$(echo $replicas | cut -d'/' -f2)
            
            if [ "$running" != "$desired" ]; then
                all_running=false
                echo "Service $name: $running/$desired replicas running"
                break
            fi
        done <<< "$services"
        
        if [ "$all_running" = true ]; then
            return 0
        fi
        
        sleep 10
        retries=$((retries + 1))
    done
    
    return 1
}

# Wait for services to be ready
if check_services; then
    echo "Deployment complete! All services are running."
    echo "Monitor logs with: docker service logs -f objectstore_orchestrator"
else
    echo "Error: Some services failed to start. Check logs for details."
    docker service ls
    exit 1
fi
