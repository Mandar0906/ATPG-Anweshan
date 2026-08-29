# Build context is the repo root (see docker-compose.yml) so this can pull in db/ too.
FROM python:3.11-slim

WORKDIR /srv

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY db/ db/
COPY backend/ backend/

WORKDIR /srv/backend
RUN chmod +x entrypoint.sh

# db/apply_schema.py and db/seed.py are run relative to /srv, not /srv/backend --
# entrypoint.sh cds appropriately via relative "db/..." paths from /srv.
WORKDIR /srv

EXPOSE 8000
CMD ["backend/entrypoint.sh"]
