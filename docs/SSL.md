# ArbiCore X — SSL.md

TLS termination is at the compose `nginx` service; certificates are issued and renewed by the `certbot` service via HTTP-01 challenges over `/.well-known/acme-challenge/`.

## 1. First-time issuance (part of `install.sh`)

1. Compose brings up `nginx` on `:80` first (still no cert on disk — the site config's `:443` block would fail `nginx -t` if we tried to load it).
2. `deployment/ssl/init-letsencrypt.sh` runs certbot in `certonly --webroot` mode:
   - **Default `LETSENCRYPT_MODE=staging`** — uses Let's Encrypt's staging endpoint. Rate-limit-safe. Cert is signed by the staging CA (browsers will warn).
   - `LETSENCRYPT_MODE=prod` — uses the production endpoint. Rate limits apply (5 duplicate certs / week; 50 certs per registered domain / week).
3. On success, certs land at `/etc/letsencrypt/live/${DOMAIN}/{fullchain,privkey,chain}.pem` inside the `arbicore-x-certbot-etc` volume, shared read-only with nginx.
4. Nginx is reloaded — the `:443` block now loads and serves TLS.

## 2. Flipping staging → prod

Always start with staging. Once `https://${DOMAIN}` loads with a staging cert:

```bash
cd /opt/arbicore-x
sed -i 's/^LETSENCRYPT_MODE=.*/LETSENCRYPT_MODE=prod/' .env

# Remove the staging cert so certbot re-issues a real one on the next run
DOMAIN_VAL=$(grep '^DOMAIN=' .env | cut -d= -f2)
docker exec arbicore-x-certbot certbot delete --cert-name "${DOMAIN_VAL}" --non-interactive

./deployment/ssl/init-letsencrypt.sh
docker compose -f deployment/compose/docker-compose.yml restart nginx
```

Verify:

```bash
echo | openssl s_client -servername "$DOMAIN_VAL" -connect "${DOMAIN_VAL}:443" 2>/dev/null \
  | openssl x509 -noout -issuer -dates
# Expect: issuer = C = US, O = Let's Encrypt, CN = R3
```

## 3. Automated renewal

Renewals happen inside the running `certbot` container, which loops:

```
while :; do certbot renew --webroot -w /var/www/certbot --quiet; sleep 12h & wait; done
```

That handles renewal, but does not reload nginx. So we ALSO install a host-level cron that does both explicitly:

```bash
sudo bash -c 'cat /opt/arbicore-x/deployment/ssl/cronjob.example >> /etc/crontab'
systemctl reload cron
```

Which executes:

```
17 3 * * * /opt/arbicore-x/deployment/ssl/renew.sh
```

`renew.sh` runs `certbot renew` inside the certbot container, then `nginx -s reload`.

## 4. Manual renewal (troubleshooting)

```bash
cd /opt/arbicore-x/deployment/compose
docker compose exec certbot certbot certificates            # inspect current certs
docker compose exec certbot certbot renew --dry-run         # test renewal
docker compose exec certbot certbot renew                    # actual renewal (only if <30d)
docker compose exec nginx nginx -s reload                   # activate renewed cert
```

## 5. TLS baseline

`deployment/nginx/snippets/ssl.conf` — Mozilla Intermediate profile (as of Feb 2026):

- Protocols: **TLSv1.2 + TLSv1.3** only (TLS 1.0/1.1 disabled)
- Ciphers: AEAD only (GCM + CHACHA20-POLY1305)
- Session cache: 10 MB shared, 1-day timeout
- OCSP stapling: **on**, `verify=on`, resolver 1.1.1.1 / 8.8.8.8

## 6. Security headers

`deployment/nginx/snippets/security_headers.conf`:

- `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- `X-Frame-Options: SAMEORIGIN`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()`
- Baseline CSP (adjust `connect-src` once the API + WS origin inventory is stable)

Test with:

```bash
curl -sk -I https://${DOMAIN} | grep -iE "strict-transport-security|x-frame-options|x-content-type-options|content-security-policy"
```

Or use Mozilla Observatory / SSL Labs (`https://www.ssllabs.com/ssltest/`) after prod cert issuance.

## 7. Common failures

| Symptom | Cause | Fix |
|---|---|---|
| certbot: "DNS problem: NXDOMAIN looking up A for ${DOMAIN}" | DNS not propagated | Wait, then verify with `dig +short ${DOMAIN}` |
| certbot: "urn:ietf:params:acme:error:rateLimited" | Too many prod certs issued | Wait ≥ 1 week or use staging until issues are resolved |
| certbot: "Some challenges have failed" (invalid response 404) | Nginx not serving `/.well-known/acme-challenge/` | Check nginx :80 block has the challenge location; check `arbicore-x-certbot-www` volume is mounted |
| `nginx -t` fails "cannot load certificate" after cert delete | Site config references cert files that no longer exist | Bring nginx up HTTP-only first, re-issue cert, then reload |
| Browser: "NET::ERR_CERT_AUTHORITY_INVALID" | Still on staging cert | Flip to prod per §2 |

## 8. Rotation / disaster

Cert issuance is idempotent. If certs are lost:

```bash
# Purge the certbot volume
docker volume rm arbicore-x-certbot-etc arbicore-x-certbot-www
# Re-init
./deployment/ssl/init-letsencrypt.sh
docker compose -f deployment/compose/docker-compose.yml restart nginx
```
