#!/bin/bash

apt update && apt upgrade -y
apt install -y git

# Hardening
mkdir -p /home/ubuntu/polylab
cd /home/ubuntu/polylab
git clone https://github.com/konstruktoid/hardening
cd hardening
chmod +x ubuntu.sh
./ubuntu.sh

# Install Docker
apt-get install -y docker.io
systemctl enable docker
systemctl start docker

# Install Trivy
snap install trivy

docker pull python:slim-buster
trivy image --format json --output /home/ubuntu/cve.json python:slim-buster

# Install OSSEC
docker run -d \
  --name ossec-server \
  -p 1514:1514/udp \
  -p 1515:1515 \
  -p 514:514/udp \
  -p 55000:55000 \
  atomicorp/ossec-docker

# Install Elasticsearch
sudo docker run -d \
  --name elasticsearch \
  -p 9200:9200 \
  -p 9300:9300 \
  -e "discovery.type=single-node" \
  -e "xpack.security.enabled=false" \
  -e "ES_JAVA_OPTS=-Xms256m -Xmx256m" \
  docker.elastic.co/elasticsearch/elasticsearch:7.17.10