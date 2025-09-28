# Instagram Worker User Setup

This document describes the security improvements made to run your Instagram worker processes with a dedicated non-root user instead of using the root profile.

## 🔒 Security Improvements

### Before
- Worker processes ran as root user
- Potential security risks from elevated privileges
- No privilege separation

### After
- Dedicated `instagram-worker` user with minimal required privileges
- Containers run as non-root user
- Added security constraints to prevent privilege escalation
- Proper file permissions and ownership

## 👤 User Details

- **Username**: `instagram-worker`
- **Type**: System user (no login shell)
- **Home Directory**: `/var/www/instachatico`
- **Groups**: `instagram-worker`, `docker`
- **UID**: Assigned by system (typically 1000+)

## 📁 Directory Structure & Permissions

```
/var/www/instachatico/app/
├── conversations/          # SQLite databases (755, instagram-worker:instagram-worker)
├── core/                  # Application code (755, instagram-worker:instagram-worker)
├── celery_worker.py       # Executable worker script (755, instagram-worker:instagram-worker)
└── ...                    # Other files (644, instagram-worker:instagram-worker)
```

## 🐳 Docker Configuration Changes

### Dockerfile Updates
- Added user creation: `RUN groupadd -r instagram-worker && useradd -r -g instagram-worker instagram-worker`
- Set ownership: `RUN chown -R instagram-worker:instagram-worker /app`
- Switch to user: `USER instagram-worker`

### Docker Compose Updates
- Added security option: `security_opt: - no-new-privileges:true`
- Applied to all application containers (api, celery_worker, celery_beat)

## 🚀 Deployment Steps

### 1. Run Setup Script
```bash
sudo /var/www/instachatico/app/setup-worker-user.sh
```

### 2. Rebuild Containers
```bash
cd /var/www/instachatico/app
docker-compose build
```

### 3. Restart Services
```bash
docker-compose down
docker-compose up -d
```

### 4. Verify Setup
```bash
# Check container user
docker-compose exec api whoami
docker-compose exec celery_worker whoami

# Check file permissions
ls -la /var/www/instachatico/app/conversations/

# Check container processes
docker-compose ps
```

## 🔍 Required Permissions

The `instagram-worker` user has been granted the following permissions:

### File System Access
- **Read/Write**: `/var/www/instachatico/app/conversations/` (SQLite databases)
- **Read**: `/var/www/instachatico/app/` (application code)
- **Execute**: `/var/www/instachatico/app/celery_worker.py`

### Network Access
- **PostgreSQL**: Connection to `instagram_postgres` container
- **Redis**: Connection to `instagram_redis` container
- **External APIs**: Instagram, Telegram, OpenAI APIs

### Docker Access
- **Group membership**: `docker` group for container operations

## 🧪 Testing

The setup script includes automated tests for:
- Directory access and creation
- SQLite database creation
- File permission verification

## 🔧 Troubleshooting

### Permission Denied Errors
```bash
# Check file ownership
ls -la /var/www/instachatico/app/

# Fix ownership if needed
sudo chown -R instagram-worker:instagram-worker /var/www/instachatico/app
```

### Container Won't Start
```bash
# Check container logs
docker-compose logs api
docker-compose logs celery_worker

# Verify user exists
id instagram-worker
```

### Database Connection Issues
```bash
# Check PostgreSQL container
docker-compose exec postgres psql -U lun1z -d instagram_db -c "SELECT 1;"

# Check Redis container
docker-compose exec redis redis-cli ping
```

## 📊 Security Benefits

1. **Principle of Least Privilege**: User only has access to required resources
2. **Container Security**: Non-root execution prevents privilege escalation
3. **File System Protection**: Proper ownership and permissions
4. **Network Isolation**: Containers communicate through defined networks
5. **Audit Trail**: Clear ownership of files and processes

## 🔄 Rollback (if needed)

If you need to revert to root user:

1. Edit `Dockerfile` and remove the `USER instagram-worker` line
2. Remove `security_opt` from `docker-compose.yml`
3. Rebuild and restart containers

## 📞 Support

If you encounter any issues with this setup:
1. Check the container logs: `docker-compose logs`
2. Verify file permissions: `ls -la /var/www/instachatico/app/`
3. Test user access: `sudo -u instagram-worker ls /var/www/instachatico/app/`

---

**Note**: This setup follows Docker security best practices and significantly improves the security posture of your Instagram worker application.
