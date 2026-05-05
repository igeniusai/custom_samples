#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

CA_CN="TestLocalCA"
CA_DAYS=1826
CERT_NAME="server_cert"
CERT_CN="test.local"
CERT_DAYS=825
CERT_SAN="DNS:*.local"
KEY_SIZE=2048

usage() {
  echo "Usage: $0 [OPTIONS]"
  echo ""
  echo "Options:"
  echo "  --ca-cn     CN for the CA certificate        (default: $CA_CN)"
  echo "  --ca-days   CA cert validity in days         (default: $CA_DAYS)"
  echo "  --cert-name Output file prefix               (default: $CERT_NAME)"
  echo "  --cert-cn   CN for the server certificate    (default: $CERT_CN)"
  echo "  --cert-days Server cert validity in days     (default: $CERT_DAYS)"
  echo "  --cert-san  Subject Alternative Names        (default: $CERT_SAN)"
  echo "  --key-size  RSA key size in bits             (default: $KEY_SIZE)"
  echo ""
  echo "Examples:"
  echo "  $0 --cert-name myservice --cert-cn myservice.local --cert-san DNS:myservice.local"
  echo "  $0 --cert-san 'DNS:*.local,DNS:localhost,IP:127.0.0.1'"
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ca-cn)     CA_CN="$2";     shift 2 ;;
    --ca-days)   CA_DAYS="$2";   shift 2 ;;
    --cert-name) CERT_NAME="$2"; shift 2 ;;
    --cert-cn)   CERT_CN="$2";   shift 2 ;;
    --cert-days) CERT_DAYS="$2"; shift 2 ;;
    --cert-san)  CERT_SAN="$2";  shift 2 ;;
    --key-size)  KEY_SIZE="$2";  shift 2 ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

# Generate CA private key
openssl genrsa -out "$ROOT_DIR/certs/ca.key" "$KEY_SIZE"

# Generate CA certificate (import this into browsers/OS to trust the server cert)
openssl req -new -x509 -days "$CA_DAYS" -key "$ROOT_DIR/certs/ca.key" -out "$ROOT_DIR/certs/ca.crt" \
  -subj "/CN=$CA_CN"

# Generate server private key
openssl genrsa -out "$ROOT_DIR/certs/${CERT_NAME}.key" "$KEY_SIZE"

# Generate a certificate signing request (CSR)
openssl req -new -key "$ROOT_DIR/certs/${CERT_NAME}.key" -out "$ROOT_DIR/certs/${CERT_NAME}.csr" \
  -subj "/CN=$CERT_CN"

# Sign it with the CA
openssl x509 -req \
  -in "$ROOT_DIR/certs/${CERT_NAME}.csr" \
  -CA "$ROOT_DIR/certs/ca.crt" \
  -CAkey "$ROOT_DIR/certs/ca.key" \
  -CAcreateserial \
  -out "$ROOT_DIR/certs/${CERT_NAME}.crt" \
  -days "$CERT_DAYS" \
  -sha256 \
  -extfile <(printf "subjectAltName=%s\nkeyUsage=digitalSignature\nextendedKeyUsage=serverAuth" "$CERT_SAN")
