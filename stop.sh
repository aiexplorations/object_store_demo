#!/bin/bash

echo "Stopping Object Store deployment..."

# Remove the stack
docker stack rm objectstore

# Wait for services to be removed
echo "Waiting for services to be removed..."
sleep 10

# Leave swarm mode
echo "Leaving swarm mode..."
docker swarm leave --force

# Stop and remove the local registry
echo "Stopping local registry..."
docker stop registry && docker rm registry

# Clean up any leftover containers
echo "Cleaning up containers..."
docker container prune -f

# Clean up any unused networks
echo "Cleaning up networks..."
docker network prune -f

# Remove local images
echo "Removing local images..."
docker rmi localhost:5000/object-receiver:latest
docker rmi localhost:5000/object-getter:latest
docker rmi localhost:5000/orchestrator:latest

echo "Cleanup complete!"
