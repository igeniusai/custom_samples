#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

NAMESPACE="test"
SECRET_NAME="tls-secret"
CERT_NAME="server_cert"

usage() {
  echo "Usage: $0 [OPTIONS]"
  echo ""
  echo "Options:"
  echo "  --namespace    Kubernetes namespace to create the secret in  (default: $NAMESPACE)"
  echo "  --secret-name  Name of the Kubernetes TLS secret             (default: $SECRET_NAME)"
  echo "  --cert-name    File prefix of the cert/key pair to load      (default: $CERT_NAME)"
  echo ""
  echo "Examples:"
  echo "  $0 --namespace prod --secret-name myservice-tls --cert-name myservice"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace)   NAMESPACE="$2";   shift 2 ;;
    --secret-name) SECRET_NAME="$2"; shift 2 ;;
    --cert-name)   CERT_NAME="$2";   shift 2 ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

kubectl delete secret "$SECRET_NAME" -n "$NAMESPACE" --ignore-not-found=true
kubectl create secret tls "$SECRET_NAME" \
  --cert="$ROOT_DIR/certs/${CERT_NAME}.crt" \
  --key="$ROOT_DIR/certs/${CERT_NAME}.key" \
  -n "$NAMESPACE"
