# Issues - README Update Evidence Collection

## Discrepancies Found
- **API Endpoint Mismatch**: README shows `/chat/query` (Line 137), but actual is `/chat` and `/chat/stream`.
- **Port Mismatch**: README shows Embedding API on 8001, but `docker-compose.yml` uses 8003.
- **Conda Env Mismatch**: README uses `ddoksori`, but `.agent/rules/environment.md` mandates `dsr`.
- **Broken Links**: 7 out of 9 documentation links in README are broken.
- **Missing Configuration**: README lacks an environment variables section, making initial setup difficult for new users.
- **Missing Services**: Redis, Prometheus, and Grafana are not mentioned in the README architecture/tech stack despite being in `docker-compose.yml`.
