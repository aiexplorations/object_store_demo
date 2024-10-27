#!/bin/bash

# Add error handling
set -e  # Exit on error

echo "Stopping Object Store deployment..."

# Remove the stack
echo "Removing stack..."
docker stack rm objectstore || true

# Wait for services to be removed
echo "Waiting for services to be removed..."
sleep 30  # Increased wait time for proper cleanup

# Verify all services are removed
while docker stack ps objectstore 2>/dev/null | grep -q .; do
    echo "Waiting for services to be fully removed..."
    sleep 5
done

# Leave swarm mode
echo "Leaving swarm mode..."
docker swarm leave --force || true

# Stop and remove the local registry
echo "Stopping local registry..."
docker stop registry && docker rm registry || true

# Clean up any leftover containers
echo "Cleaning up containers..."
docker container prune -f

# Clean up networks
echo "Cleaning up networks..."
docker network prune -f  # This is sufficient now

# Clean up MinIO volumes
echo "Cleaning up MinIO volumes..."
for i in {1..4}; do
    docker volume rm "objectstore_minio_data${i}" 2>/dev/null || true
done

# Remove local images
echo "Removing local images..."
for image in object-receiver object-getter orchestrator; do
    docker rmi "localhost:5000/${image}:latest" 2>/dev/null || true
done

echo "Cleanup complete!"
