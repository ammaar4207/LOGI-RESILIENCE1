#!/bin/bash

# Logi-Resilience Ultimate Enterprise Kubernetes Deployment Script
# This script provisions the local Minikube cluster and deploys the entire full-stack application.

echo "🚀 [1/5] Starting Minikube cluster with optimized resource allocation..."
minikube start --cpus 3 --memory 5120 --disk-size 30g
minikube addons enable ingress

echo "📦 [2/5] Updating Helm Chart Dependencies (Kafka, Redis, Postgres, Neo4j)..."
cd k8s/helm-chart
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add neo4j https://helm.neo4j.com/neo4j
helm repo update
helm dependency update

echo "🏗️ [3/5] Building local Docker images into Minikube environment..."
eval $(minikube docker-env)
# Build exactly as we do for docker-compose, but the images go into Minikube's Docker daemon
docker build -t logi-resilience-backend:latest ../../backend
docker build -t logi-resilience-frontend:latest ../../frontend

echo "🚀 [4/5] Deploying Logi-Resilience Enterprise Helm Chart..."
# Install the chart using Helm
helm upgrade --install logi-resilience . \
  --namespace logi-resilience \
  --create-namespace \
  --set global.postgresql.auth.postgresPassword=mca_postgres_password_2026 \
  --set global.redis.auth.password=mca_redis_password_2026 \
  --set neo4j.neo4j.password=mca_secure_password_2026

echo "✅ [5/5] Deployment Initiated!"
echo "Check pod status with: kubectl get pods -n logi-resilience -w"
echo "To access the UI, run: minikube service logi-resilience-frontend -n logi-resilience"
