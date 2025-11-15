# aws-cloud-security

A practical AWS cloud security project focused on building and securing cloud infrastructure.  
Includes VPC configuration, EC2 hardening, network security controls, logging, and monitoring.

### **VPC Security**
- Network segmentation  
- Security groups & NACLs  
- VPC Flow Logs (S3 / parquet)

### **EC2 Security**
- Ubuntu hardening (konstruktoid)  
- Windows Defender & Firewall  
- OSSEC agents  
- Docker Scan & Trivy  

### **Architecture & Compliance**
- CSA compliance analysis  
- Secure AWS architecture design  
- CloudWatch & CloudTrail monitoring setup  

## Project Structure

aws-cloud-security/
│── cleanup.py       # Delete used resources on AWS<br>
│── architecture.png # Secure architecture design  <br>
│── main.py          # EC2 deployment & hardening  <br>
└── README.md

## Technologies
- AWS VPC  
- EC2 (Ubuntu & Windows)  
- CloudWatch / CloudTrail  
- OSSEC  
- Elasticsearch  
- Docker Scan & Trivy 