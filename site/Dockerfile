# Bedtime study page: production container. Docker only sees public/, never a working folder.
FROM caddy:2-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY public /srv
EXPOSE 8080
