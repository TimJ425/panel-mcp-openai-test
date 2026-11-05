#!/usr/bin/env bash
# Create a local CA + a localhost server cert for the fake micro service.
# certs/ca.pem is the CA bundle the MCP server uses as proxy_cert.
set -euo pipefail
mkdir -p "$(dirname "$0")/../certs"; cd "$(dirname "$0")/../certs"
[[ -f server.pem ]] && { echo "certs exist"; exit 0; }

openssl req -x509 -newkey rsa:2048 -nodes -days 825 -subj "/CN=Local Test CA" \
  -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign" -addext "subjectKeyIdentifier=hash" \
  -keyout ca.key -out ca.pem 2>/dev/null
openssl req -newkey rsa:2048 -nodes -subj "/CN=localhost" -keyout server.key -out server.csr 2>/dev/null
printf "subjectAltName=DNS:localhost,IP:127.0.0.1\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n" > ext.cnf
openssl x509 -req -in server.csr -CA ca.pem -CAkey ca.key -CAcreateserial -days 825 -extfile ext.cnf -out server.pem 2>/dev/null
rm -f server.csr ext.cnf ca.srl
echo "certs created in $(pwd)"
