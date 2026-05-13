#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

NAMESPACE="test"
SECRET_NAME="tls-secret"
CERT_NAME="server_cert"
CONTEXT=""

usage() {
  echo "Usage: $0 [OPTIONS]"
  echo ""
  echo "Options:"
  echo "  --namespace    Kubernetes namespace to create the secret in  (default: $NAMESPACE)"
  echo "  --secret-name  Name of the Kubernetes TLS secret             (default: $SECRET_NAME)"
  echo "  --cert-name    File prefix of the cert/key pair to load      (default: $CERT_NAME)"
  echo "  --context      kubectl context to use                        (default: current context)"
  echo ""
  echo "Examples:"
  echo "  $0 --namespace prod --secret-name myservice-tls --cert-name myservice"
  echo "  $0 --context my-cluster --namespace prod --secret-name myservice-tls"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace)   NAMESPACE="$2";   shift 2 ;;
    --secret-name) SECRET_NAME="$2"; shift 2 ;;
    --cert-name)   CERT_NAME="$2";   shift 2 ;;
    --context)     CONTEXT="$2";     shift 2 ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

KUBECTL_OPTS=(-n "$NAMESPACE")
[[ -n "$CONTEXT" ]] && KUBECTL_OPTS+=(--context "$CONTEXT")

kubectl delete secret "$SECRET_NAME" "${KUBECTL_OPTS[@]}" --ignore-not-found=true
kubectl create secret tls "$SECRET_NAME" \
  --cert="$ROOT_DIR/certs/${CERT_NAME}.crt" \
  --key="$ROOT_DIR/certs/${CERT_NAME}.key" \
  "${KUBECTL_OPTS[@]}"
