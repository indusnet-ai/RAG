# 🚀 RAG Chatbot Deployment Guide for `indusnetai.com`

This guide explains how to deploy the containerized RAG application on your remote server and configure it under your domain `indusnetai.com` (or `rag.indusnetai.com`) for online testing.

---

## 📌 Prerequisites on Server

1. **Ubuntu / Linux Server** with Docker & Docker Compose installed:
   ```bash
   sudo apt-get update
   sudo apt-get install -y docker.io docker-compose-v2 nginx certbot python3-certbot-nginx
   sudo systemctl enable --now docker
   ```
2. **DNS Configuration**:
   - Point an **A Record** for `indusnetai.com` (or `rag.indusnetai.com`) to your server's Public IP address in your DNS provider.

---

## 🛠️ Step 1: Transfer & Setup Code on Server

Clone your repository to the server:
```bash
git clone https://github.com/indusnet-ai/RAG.git
cd RAG
```

Create your `.env` configuration file:
```bash
cp .env.docker.example .env
nano .env
```
*(Enter your `OPENAI_API_KEY`, `JWT_SECRET`, and optional `LANGCHAIN_API_KEY`)*

---

## 🐳 Step 2: Build & Start Docker Containers

Run the following command to build and launch the application:
```bash
docker compose up -d --build
```

Verify that both containers (`rag_backend` and `rag_frontend`) are running cleanly:
```bash
docker compose ps
```

You can test local container endpoints on the server:
- **Frontend UI**: `http://localhost:80`
- **FastAPI Backend Docs**: `http://localhost:8000/docs`

---

## 🔒 Step 3: Configure Host Nginx & HTTPS (SSL) for `indusnetai.com`

To make the application securely accessible at `https://indusnetai.com` (or `https://rag.indusnetai.com`), set up a reverse proxy on your server's host Nginx.

Create a new Nginx site config:
```bash
sudo nano /etc/nginx/sites-available/indusnetai
```

Paste the following configuration (replace `indusnetai.com` with your exact domain or subdomain):

```nginx
server {
    listen 80;
    server_name indusnetai.com www.indusnetai.com rag.indusnetai.com;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:80;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE / Streaming support
        proxy_buffering off;
        proxy_read_timeout 300s;
    }
}
```

Enable the site and test configuration:
```bash
sudo ln -s /etc/nginx/sites-available/indusnetai /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Enable Free SSL Certificate (Let's Encrypt / Certbot)

Run Certbot to automatically configure HTTPS SSL:
```bash
sudo certbot --nginx -d indusnetai.com -d www.indusnetai.com -d rag.indusnetai.com
```

Now your application is live and secure at **`https://indusnetai.com`**! 🎉

---

## 📋 Useful Server Maintenance Commands

| Action | Command |
|--------|---------|
| **View Live Backend Logs** | `docker compose logs -f backend` |
| **View Live Frontend Logs** | `docker compose logs -f frontend` |
| **Restart Containers** | `docker compose restart` |
| **Rebuild & Update** | `git pull && docker compose up -d --build` |
| **Stop Containers** | `docker compose down` |
| **Check Data Persistence** | Uploaded files persist in `./uploaded_files/` and SQLite DB in `./rag_local.db` |
