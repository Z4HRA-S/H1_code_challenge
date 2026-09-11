#!/bin/bash

set -e

IMAGE_NAME="api-consumer:latest"
CONFIG_NAME="api-consumer-config"

echo "Starting Minikube..."
minikube start

echo "Building image..."
minikube image build -t "$IMAGE_NAME" .

echo "Updating ConfigMap..."
kubectl create configmap "$CONFIG_NAME" \
    --from-file=config.yaml \
    --dry-run=client \
    -o yaml | kubectl apply -f -

echo "Removing previous Job..."
kubectl delete job api-consumer --ignore-not-found

echo "Starting client..."
kubectl apply -f manifests/job.yaml

echo "Waiting for completion..."
kubectl wait \
    --for=condition=complete \
    job/api-consumer \
    --timeout=120s

echo "Client output:"
kubectl logs job/api-consumer