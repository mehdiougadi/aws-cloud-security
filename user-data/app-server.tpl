#!/bin/bash
# Hardened Ubuntu setup for App Server AZ2 with Docker-scan and Trivy

apt update && apt upgrade -y
apt install -y git

# Hardening
mkdir -p /home/ubuntu/polylab
cd /home/ubuntu/polylab
git clone https://github.com/konstruktoid/hardening
cd hardening && ./ubuntu.sh

# Install Docker
apt-get install -y ca-certificates curl gnupg lsb-release
mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
systemctl enable docker
systemctl start docker

# Install Trivy
wget -qO - https://aquasecurity.github.io/trivy-repo/deb/public.key | apt-key add -
echo "deb https://aquasecurity.github.io/trivy-repo/deb $(lsb_release -sc) main" | tee -a /etc/apt/sources.list.d/trivy.list
apt-get update
apt-get install -y trivy

# Test installations
docker pull python:slim-buster
trivy image --format json --output /home/ubuntu/cve.json python:slim-buster

echo "App Server setup completed" > /home/ubuntu/init-complete.log