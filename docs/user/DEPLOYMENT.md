# Session Buddy - Deployment Guide

Comprehensive deployment strategies for the Session Management MCP server across different environments and platforms.

## Overview

The Session Management MCP server can be deployed in various configurations, from simple local development setups to enterprise-scale distributed systems.

## Deployment Strategies

### 1. Local Development

**Single-user, single-machine setup for development.**

#### Standard Installation

```bash
# Clone repository
git clone https://github.com/lesleslie/session-buddy.git
cd session-buddy

# Install with UV (recommended)
uv sync

# Verify installation
python -c "from session_buddy.server import mcp; print('✅ Ready')"
```

#### Claude Code Configuration

```json
# .mcp.json
{
  "mcpServers": {
    "session-buddy": {
      "command": "python",
      "args": ["-m", "session_buddy.server"],
      "cwd": "/absolute/path/to/session-buddy",
      "env": {
        "PYTHONPATH": "/absolute/path/to/session-buddy",
        "SESSION_BUDDY_LOG_LEVEL": "DEBUG"
      }
    }
  }
}
```

#### Development Environment Variables

```bash
# .env.development
export SESSION_BUDDY_LOG_LEVEL=DEBUG
export SESSION_BUDDY_DATA_DIR="$HOME/.claude/data"
export SESSION_BUDDY_EMBEDDING_CACHE_SIZE=100
```

### 2. Production Single Server

**Single-server production deployment with systemd.**

#### System Service Setup

```bash
# Create dedicated user
sudo useradd --system --shell /bin/false --home /opt/session-buddy session-buddy

# Create directories
sudo mkdir -p /opt/session-buddy/{app,data,logs}
sudo chown -R session-buddy:session-buddy /opt/session-buddy
```

#### Systemd Service

```ini
# /etc/systemd/system/session-buddy.service
[Unit]
Description=Session Management MCP Server
After=network.target
Wants=network.target

[Service]
Type=simple
User=session-buddy
Group=session-buddy
WorkingDirectory=/opt/session-buddy/app
Environment=SESSION_BUDDY_DATA_DIR=/opt/session-buddy/data
Environment=SESSION_BUDDY_LOG_DIR=/opt/session-buddy/logs
Environment=SESSION_BUDDY_LOG_LEVEL=INFO
Environment=PYTHONPATH=/opt/session-buddy/app
ExecStart=/opt/session-buddy/app/.venv/bin/python -m session_buddy.server
ExecReload=/bin/kill -HUP $MAINPID
KillMode=mixed
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

# Security settings
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/opt/session-buddy/data /opt/session-buddy/logs
PrivateTmp=yes
ProtectKernelTunables=yes
ProtectControlGroups=yes

[Install]
WantedBy=multi-user.target
```

#### Deployment Script

```bash
#!/bin/bash
# deploy-production.sh

set -e

APP_DIR="/opt/session-buddy/app"
DATA_DIR="/opt/session-buddy/data"
LOG_DIR="/opt/session-buddy/logs"

echo "🚀 Deploying Session Management MCP Server"

# Stop service if running
sudo systemctl stop session-buddy || true

# Backup current deployment
if [ -d "$APP_DIR" ]; then
    sudo cp -r "$APP_DIR" "$APP_DIR.backup.$(date +%Y%m%d_%H%M%S)"
fi

# Deploy new version
sudo rm -rf "$APP_DIR"
sudo -u session-buddy git clone https://github.com/lesleslie/session-buddy.git "$APP_DIR"
sudo -u session-buddy bash -c "cd $APP_DIR && uv sync"

# Set permissions
sudo chown -R session-buddy:session-buddy "$APP_DIR"
sudo chmod +x "$APP_DIR/scripts/"*.sh

# Create directories
sudo mkdir -p "$DATA_DIR" "$LOG_DIR"
sudo chown -R session-buddy:session-buddy "$DATA_DIR" "$LOG_DIR"

# Reload and start service
sudo systemctl daemon-reload
sudo systemctl enable session-buddy
sudo systemctl start session-buddy

# Health check
sleep 5
if sudo systemctl is-active --quiet session-buddy; then
    echo "✅ Deployment successful"
else
    echo "❌ Deployment failed"
    sudo journalctl -u session-buddy --lines=20
    exit 1
fi
```

### 3. Docker Deployment

**Containerized deployment for consistency and portability.**

#### Dockerfile

```dockerfile
FROM python:3.13-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create app user
RUN groupadd --system app && useradd --system --group app

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY pyproject.toml uv.lock ./

# Install UV and dependencies
RUN pip install uv
RUN uv sync --no-dev

# Copy application code
COPY . .

# Set ownership
RUN chown -R app:app /app

# Create data directory
RUN mkdir -p /data && chown app:app /data

# Switch to app user
USER app

# Environment variables
ENV SESSION_BUDDY_DATA_DIR=/data
ENV SESSION_BUDDY_LOG_LEVEL=INFO
ENV PYTHONPATH=/app

# Start server
ENTRYPOINT ["python", "-m", "session_buddy.server"]
```

#### Docker Compose

```yaml
# docker-compose.yml
version: '3.8'

services:
  session-buddy:
    build: .
    container_name: session-buddy
    restart: unless-stopped
    environment:
      - SESSION_BUDDY_DATA_DIR=/data
      - SESSION_BUDDY_LOG_LEVEL=INFO
      - SESSION_BUDDY_EMBEDDING_CACHE_SIZE=1000
    volumes:
      - session_data:/data
      - session_logs:/logs

  # Optional: Redis for caching
  redis:
    image: redis:7-alpine
    container_name: session-buddy-redis
    restart: unless-stopped
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes

  # Optional: PostgreSQL for external storage
  postgres:
    image: postgres:15-alpine
    container_name: session-buddy-postgres
    restart: unless-stopped
    environment:
      - POSTGRES_DB=sessionmgmt
      - POSTGRES_USER=sessionuser
      - POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    secrets:
      - postgres_password

volumes:
  session_data:
    driver: local
  session_logs:
    driver: local
  redis_data:
    driver: local
  postgres_data:
    driver: local

secrets:
  postgres_password:
    file: ./secrets/postgres_password.txt
```

#### Docker Deployment Script

```bash
#!/bin/bash
# docker-deploy.sh

set -e

echo "🐳 Deploying Session Management MCP with Docker"

# Create secrets directory
mkdir -p secrets
echo "$(openssl rand -base64 32)" > secrets/postgres_password.txt
chmod 600 secrets/postgres_password.txt

# Build and deploy
docker compose build --no-cache
docker compose up -d

# Wait for services
echo "⏳ Waiting for services to start..."
sleep 30

# Health check
if docker compose ps | grep -q "Up"; then
    echo "✅ Docker deployment successful"
    docker compose ps
else
    echo "❌ Docker deployment failed"
    docker compose logs
    exit 1
fi

# Show logs
echo "📋 Service logs:"
docker compose logs --tail=20 session-buddy
```

### 4. Kubernetes Deployment

Kubernetes deployment is supported for containerized usage, but the server does not expose HTTP health, metrics, or TLS endpoints. Use exec-based health checks (import or CLI) and standard reverse proxies if you need TLS termination.

### 5. Cloud Platform Deployments

#### AWS ECS Deployment

```json
{
  "family": "session-buddy",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "executionRoleArn": "arn:aws:iam::account:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::account:role/ecsTaskRole",
  "containerDefinitions": [
    {
      "name": "session-buddy",
      "image": "your-account.dkr.ecr.region.amazonaws.com/session-buddy:latest",
      "essential": true,
      ],
      "environment": [
        {
          "name": "SESSION_BUDDY_DATA_DIR",
          "value": "/data"
        },
        {
          "name": "SESSION_BUDDY_LOG_LEVEL",
          "value": "INFO"
        }
      ],
      "secrets": [
        {
          "name": "DATABASE_URL",
          "valueFrom": "arn:aws:secretsmanager:region:account:secret:session-buddy/database-url"
        }
      ],
      "mountPoints": [
        {
          "sourceVolume": "session-data",
          "containerPath": "/data"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/session-buddy",
          "awslogs-region": "us-west-2",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": [
          "CMD-SHELL",
          "python -c 'import session_buddy.server; print(\"healthy\")'"
        ],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 60
      }
    }
  ],
  "volumes": [
    {
      "name": "session-data",
      "efsVolumeConfiguration": {
        "fileSystemId": "fs-12345678",
        "rootDirectory": "/",
        "transitEncryption": "ENABLED"
      }
    }
  ]
}
```

#### Google Cloud Run Deployment

```yaml
# cloudrun.yaml
apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: session-buddy
  namespace: default
  annotations:
    run.googleapis.com/execution-environment: gen2
spec:
  template:
    metadata:
      annotations:
        autoscaling.knative.dev/minScale: "1"
        autoscaling.knative.dev/maxScale: "10"
        run.googleapis.com/cpu-throttling: "false"
        run.googleapis.com/memory: "2Gi"
        run.googleapis.com/cpu: "1000m"
    spec:
      containerConcurrency: 100
      timeoutSeconds: 300
      containers:
      - image: gcr.io/project-id/session-buddy:latest
        env:
        - name: SESSION_BUDDY_DATA_DIR
          value: "/data"
        - name: SESSION_BUDDY_LOG_LEVEL
          value: "INFO"
        - name: GOOGLE_CLOUD_PROJECT
          value: "project-id"
        volumeMounts:
        - name: session-data
          mountPath: /data
        resources:
          limits:
            memory: "2Gi"
            cpu: "1000m"
      volumes:
      - name: session-data
        csi:
          driver: gcsfuse.csi.storage.gke.io
          volumeAttributes:
            bucketName: session-buddy-data-bucket
            mountOptions: "implicit-dirs"
```

#### Azure Container Apps

```json
{
  "location": "eastus2",
  "properties": {
    "managedEnvironmentId": "/subscriptions/sub-id/resourceGroups/rg/providers/Microsoft.App/managedEnvironments/env-name",
    "configuration": {
      "secrets": [
        {
          "name": "database-url",
          "keyVaultUrl": "https://keyvault.vault.azure.net/secrets/database-url"
        }
      ],
      "registries": [
        {
          "server": "registry.azurecr.io",
          "username": "registry-username",
          "passwordSecretRef": "registry-password"
        }
      ]
    },
    "template": {
      "containers": [
        {
          "image": "registry.azurecr.io/session-buddy:latest",
          "name": "session-buddy",
          "env": [
            {
              "name": "SESSION_BUDDY_DATA_DIR",
              "value": "/data"
            },
            {
              "name": "SESSION_BUDDY_LOG_LEVEL",
              "value": "INFO"
            },
            {
              "name": "DATABASE_URL",
              "secretRef": "database-url"
            }
          ],
          "resources": {
            "cpu": 1,
            "memory": "2Gi"
          }
        }
      ],
      "scale": {
        "minReplicas": 1,
        "maxReplicas": 10,
        "rules": [
          {
            "name": "cpu-scaling",
            "custom": {
              "type": "cpu",
              "metadata": {
                "type": "Utilization",
                "value": "70"
              }
            }
          }
        ]
      }
    }
  }
}
```

## Monitoring and Observability

Session Buddy does not currently expose a metrics or health HTTP endpoint. For monitoring, rely on process-level checks, log aggregation, and periodic CLI smoke tests.

## Backup and Disaster Recovery

### Database Backup Strategy

```bash
#!/bin/bash
# backup-database.sh

set -e

BACKUP_DIR="/opt/session-buddy/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DATA_DIR="/opt/session-buddy/data"

echo "🔄 Starting database backup"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup DuckDB files
tar -czf "$BACKUP_DIR/database_$DATE.tar.gz" -C "$DATA_DIR" .

# Upload to S3 (optional)
if command -v aws >/dev/null 2>&1; then
    aws s3 cp "$BACKUP_DIR/database_$DATE.tar.gz" \
        s3://session-buddy-backups/database/
fi

# Cleanup old backups (keep 30 days)
find "$BACKUP_DIR" -name "database_*.tar.gz" -mtime +30 -delete

echo "✅ Backup completed: database_$DATE.tar.gz"
```

### Automated Backup with Cron

```bash
# Add to crontab
0 2 * * * /opt/session-buddy/scripts/backup-database.sh >> /var/log/session-buddy-backup.log 2>&1
```

### Disaster Recovery Plan

```bash
#!/bin/bash
# disaster-recovery.sh

set -e

BACKUP_FILE="$1"
DATA_DIR="/opt/session-buddy/data"
RECOVERY_DIR="/opt/session-buddy/recovery"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup-file>"
    exit 1
fi

echo "🚨 Starting disaster recovery process"

# Stop service
sudo systemctl stop session-buddy

# Create recovery directory
mkdir -p "$RECOVERY_DIR"

# Backup current state (in case recovery fails)
if [ -d "$DATA_DIR" ]; then
    mv "$DATA_DIR" "$RECOVERY_DIR/current_$(date +%Y%m%d_%H%M%S)"
fi

# Restore from backup
mkdir -p "$DATA_DIR"
tar -xzf "$BACKUP_FILE" -C "$DATA_DIR"

# Set permissions
chown -R session-buddy:session-buddy "$DATA_DIR"

# Start service
sudo systemctl start session-buddy

# Health check
sleep 10
if sudo systemctl is-active --quiet session-buddy; then
    echo "✅ Disaster recovery successful"
else
    echo "❌ Disaster recovery failed - check logs"
    sudo journalctl -u session-buddy --lines=50
    exit 1
fi
```

## Performance Optimization

### Database Optimization

```sql
-- DuckDB optimization settings
PRAGMA memory_limit='2GB';
PRAGMA threads=8;
PRAGMA checkpoint_threshold='1GB';

-- Create optimal indices
CREATE INDEX idx_conversations_project_timestamp
ON conversations(project, timestamp DESC);

CREATE INDEX idx_conversations_embedding
ON conversations USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Optimize table for vector operations
ALTER TABLE conversations
SET (embedding_compression = 'pq');
```

### Resource Limits

```yaml
# k8s resource limits
resources:
  requests:
    memory: "512Mi"
    cpu: "250m"
  limits:
    memory: "2Gi"
    cpu: "1000m"
```

## Troubleshooting

### Common Deployment Issues

#### Service Won't Start

```bash
# Check service status
sudo systemctl status session-buddy

# View logs
sudo journalctl -u session-buddy -f

# Check permissions
ls -la /opt/session-buddy/
sudo -u session-buddy python -c "import session_buddy; print('OK')"
```

#### Memory Issues

```bash
# Check memory usage
free -h
ps aux | grep session-buddy

# Reduce embedding cache size
export SESSION_BUDDY_EMBEDDING_CACHE_SIZE=500
sudo systemctl restart session-buddy
```

#### Database Connection Issues

```bash
# Check database files
ls -la /opt/session-buddy/data/

# Test database connection
sudo -u session-buddy python -c "
import duckdb
conn = duckdb.connect('/opt/session-buddy/data/reflections.db')
print('Database connection OK')
conn.close()
"
```

### Health Checks

Use process checks and a simple import test to validate basic health:

```bash
ps aux | grep session-buddy
python -c 'import session_buddy; print("OK")'
```
