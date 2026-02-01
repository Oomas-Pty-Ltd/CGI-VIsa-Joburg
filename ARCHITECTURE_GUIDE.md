# Seva Setu Bot - Production Architecture & Deployment Guide

## Current Status Summary

| Metric | Current Value | Target | Status |
|--------|---------------|--------|--------|
| Uptime | 100% | 95-98% | ✅ Exceeding |
| CPU Usage | 5% | <90% | ✅ Healthy |
| Memory Usage | 62% | <90% | ✅ Healthy |
| Disk Usage | 31% | <85% | ✅ Healthy |
| Avg Response Time | 10-12s | <30s | ✅ Normal for AI |

---

## Monitoring Endpoints

| Endpoint | Purpose | Usage |
|----------|---------|-------|
| `/api/monitoring/health` | Quick health check | Load balancers, uptime monitors |
| `/api/monitoring/status` | Dashboard summary | Admin dashboards |
| `/api/monitoring/metrics` | Detailed metrics | Grafana, monitoring tools |
| `/api/monitoring/history` | Historical data | Charting, trend analysis |
| `/api/monitoring/test-alert` | Test alerts | Verify alert configuration |

---

## Alert Configuration

### Email Alerts
Add to `/app/backend/.env`:
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
ALERT_EMAILS=admin@yourcompany.com,ops@yourcompany.com
```

### Webhook Alerts (Slack/Discord/Teams)
```
ALERT_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

### Alert Thresholds (in `/app/backend/monitoring_service.py`)
- CPU: Alert at 90%
- Memory: Alert at 90%
- Disk: Alert at 85%
- Response Time: Alert at 30s
- Cooldown: 5 minutes between same alerts

---

## Recommended Production Architecture

### For 95-98% Uptime with Good Performance

```
                    ┌─────────────────────────────────────────────┐
                    │              CLOUDFLARE CDN                 │
                    │   (DDoS Protection, SSL, Static Caching)    │
                    └─────────────────────┬───────────────────────┘
                                          │
                    ┌─────────────────────▼───────────────────────┐
                    │           LOAD BALANCER (Nginx)             │
                    │         (Health checks, SSL termination)    │
                    └───────┬─────────────────────────┬───────────┘
                            │                         │
              ┌─────────────▼──────────┐  ┌──────────▼─────────────┐
              │   APP SERVER 1         │  │   APP SERVER 2         │
              │   (Primary)            │  │   (Failover)           │
              │   ┌────────────────┐   │  │   ┌────────────────┐   │
              │   │ FastAPI Backend│   │  │   │ FastAPI Backend│   │
              │   │ (4 workers)    │   │  │   │ (4 workers)    │   │
              │   └────────────────┘   │  │   └────────────────┘   │
              │   ┌────────────────┐   │  │   ┌────────────────┐   │
              │   │ React Frontend │   │  │   │ React Frontend │   │
              │   │ (Nginx static) │   │  │   │ (Nginx static) │   │
              │   └────────────────┘   │  │   └────────────────┘   │
              └───────────┬────────────┘  └───────────┬────────────┘
                          │                           │
                          └─────────┬─────────────────┘
                                    │
              ┌─────────────────────▼─────────────────────┐
              │           MONGODB REPLICA SET             │
              │   ┌─────────┐ ┌─────────┐ ┌─────────┐    │
              │   │ Primary │ │Secondary│ │ Arbiter │    │
              │   └─────────┘ └─────────┘ └─────────┘    │
              └───────────────────────────────────────────┘
                                    │
              ┌─────────────────────▼─────────────────────┐
              │              REDIS CACHE                   │
              │       (Session cache, rate limiting)       │
              └───────────────────────────────────────────┘
```

---

## Server Specifications

### Minimum (10-50 concurrent users)
| Component | Specification |
|-----------|---------------|
| CPU | 4 vCPUs |
| RAM | 8 GB |
| Storage | 50 GB SSD |
| Bandwidth | 1 Gbps |
| OS | Ubuntu 22.04 LTS |

### Recommended (50-200 concurrent users)
| Component | Specification |
|-----------|---------------|
| CPU | 8 vCPUs |
| RAM | 16 GB |
| Storage | 100 GB NVMe SSD |
| Bandwidth | 2 Gbps |
| OS | Ubuntu 22.04 LTS |

### High Performance (200+ concurrent users)
| Component | Specification |
|-----------|---------------|
| Load Balancer | 2 vCPUs, 4 GB RAM |
| App Servers (x2) | 8 vCPUs, 16 GB RAM each |
| MongoDB Cluster | 3 nodes, 4 vCPUs, 8 GB RAM each |
| Redis | 2 vCPUs, 4 GB RAM |
| Storage | 200 GB NVMe SSD (each) |

---

## Cloud Provider Options

### Option 1: AWS (Best for Scale)
- **EC2**: t3.xlarge for app servers
- **DocumentDB**: Managed MongoDB
- **ElastiCache**: Managed Redis
- **ALB**: Application Load Balancer
- **CloudFront**: CDN
- **Estimated Cost**: $300-500/month

### Option 2: DigitalOcean (Cost-Effective)
- **Droplets**: Premium AMD, 8GB RAM
- **Managed MongoDB**: 3-node cluster
- **Load Balancer**: Built-in
- **Spaces CDN**: Static assets
- **Estimated Cost**: $150-300/month

### Option 3: Hetzner (Budget-Friendly)
- **Cloud Servers**: CPX41 (8 vCPU, 16GB)
- **Managed Database**: MongoDB
- **Load Balancer**: Cloud LB
- **Estimated Cost**: $80-150/month

### Option 4: Self-Hosted KVM (Your Request)
- **Physical Server**: Intel Xeon, 32GB RAM, 500GB NVMe
- **Proxmox/KVM**: Virtualization
- **Nginx**: Load balancer
- **Docker Swarm/K8s**: Orchestration
- **Estimated Cost**: One-time $2000-3000 + $50-100/month hosting

---

## Docker Deployment Configuration

### docker-compose.yml
```yaml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8001:8001"
    environment:
      - MONGO_URL=mongodb://mongodb:27017
      - DB_NAME=seva_setu
    depends_on:
      - mongodb
      - redis
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '2'
          memory: 4G
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/api/monitoring/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  frontend:
    build: ./frontend
    ports:
      - "3000:80"
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '1'
          memory: 1G

  mongodb:
    image: mongo:7
    volumes:
      - mongo_data:/data/db
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G

  redis:
    image: redis:7-alpine
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - backend
      - frontend

volumes:
  mongo_data:
```

---

## Performance Optimization Checklist

### Backend
- [ ] Enable Uvicorn with 4 workers: `uvicorn server:app --workers 4`
- [ ] Add Redis for session caching
- [ ] Enable gzip compression
- [ ] Add response caching for static knowledge base
- [ ] Implement connection pooling for MongoDB

### Frontend
- [ ] Build production bundle: `yarn build`
- [ ] Serve via Nginx (not React dev server)
- [ ] Enable browser caching headers
- [ ] Minify and compress assets
- [ ] Use CDN for static assets

### Database
- [ ] Create indexes on frequently queried fields
- [ ] Enable MongoDB connection pooling
- [ ] Set up replica set for high availability
- [ ] Configure automated backups

### Infrastructure
- [ ] Set up SSL/TLS certificates (Let's Encrypt)
- [ ] Configure firewall rules
- [ ] Enable DDoS protection
- [ ] Set up automated backups
- [ ] Configure log rotation

---

## External Monitoring Services (Recommended)

| Service | Purpose | Free Tier |
|---------|---------|-----------|
| **UptimeRobot** | Uptime monitoring | 50 monitors |
| **Sentry** | Error tracking | 5K events/month |
| **Grafana Cloud** | Metrics dashboard | 10K metrics |
| **PagerDuty/OpsGenie** | Alert escalation | Limited |

### Integration Example (UptimeRobot)
1. Create account at uptimerobot.com
2. Add HTTP monitor: `https://your-domain.com/api/monitoring/health`
3. Set check interval: 5 minutes
4. Configure alerts: Email, SMS, Slack

---

## Summary Recommendation

For **95-98% uptime** with your KVM server requirement:

1. **Server**: Hetzner dedicated or VPS with 8 vCPU, 16GB RAM
2. **Architecture**: Docker Compose with 2 backend replicas
3. **Database**: MongoDB replica set (3 nodes minimum)
4. **Caching**: Redis for sessions
5. **CDN**: Cloudflare (free tier works)
6. **Monitoring**: UptimeRobot + built-in monitoring
7. **Backup**: Daily automated MongoDB backups

**Estimated Monthly Cost**: $100-200/month for reliable 98% uptime
