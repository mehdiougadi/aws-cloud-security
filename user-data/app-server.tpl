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
apt-get install -y wget apt-transport-https gnupg lsb-release
wget -qO - https://aquasecurity.github.io/trivy-repo/deb/public.key | apt-key add -
echo "deb https://aquasecurity.github.io/trivy-repo/deb $(lsb_release -sc) main" | tee -a /etc/apt/sources.list.d/trivy.list
apt-get update
apt-get install -y trivy

docker pull python:slim-buster
trivy image --format json --output /home/ubuntu/cve.json python:slim-buster

echo "App Server setup completed" > /home/ubuntu/init-complete.log