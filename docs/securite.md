# Sécurité — état à la version validée (gel de version)

Vérifié dans le code et par la suite pytest (`tests/test_session.py`, `tests/test_product_rules.py`, `tests/test_alerts_crud.py`).
Secrets : `.env`, `.env.*` (dont `.env.bak`) sont ignorés par Git, seul `.env.example` est suivi, avec des valeurs locales ou vides ; l'historique Git a été balayé avant le gel (aucun secret trouvé). Les variables Neon portent des noms distincts (`NEON_DATABASE_URL`) et ne sont lues ni par le code ni par `docker-compose.yml`.

| Point | État | Où |
| --- | --- | --- |
| (a) Cookie HttpOnly, SameSite, Secure par variable, sans Max-Age si « se souvenir » décoché | OK | `backend/app/security.py` (`cookie_kwargs`, `set_session_cookie`) |
| (b) Origine étrangère / `null` refusée ; sans Origin + cookie : Sec-Fetch-Site ou Referer local ; `*.vercel.app` admis pour le site déployé | OK | `backend/app/main.py` (`reject_foreign_origin`) |
| (c) Reset / changement de mot de passe invalide les sessions (`token_version` incrémentée, vérifiée à chaque requête) | OK | `backend/app/passwords.py`, `security.py` |
| (d) Code de connexion : 6 chiffres, usage unique (`used_at`), 10 min, SHA-256 lié au compte en base, code détruit au 5e essai raté (toutes IP confondues), 5 codes / 15 min par e-mail, nouveau code invalide les anciens, connexion directe et autres sessions fermées ; code dans les logs seulement hors production ; envoi SMTP avec TLS vérifié, délai de 15 s, échec journalisé sans code ni identifiant. (Ancien lien reset 30 min conservé, plus émis.) | OK | `backend/app/passwords.py`, `routers/auth.py` |
| (e) Rate limit : login 10/min, register 10/min, forgot 5/min, chat 20/min par utilisateur | OK | `security.allow`, routeurs `auth.py` / `chat.py` |
| (f) Hachage factice si e-mail inconnu au login | OK | `security.burn_password_check` |
| (g) Google : désactivé sans les 2 variables, state signé comparé, `email_verified` exigé, pas de fusion auto (409) | OK (non testé en réel) | `routers/auth.py` |
| (h) En-têtes : `nosniff`, `Referrer-Policy`, `X-Frame-Options`, CSP stricte API / CSP site compatible Next+Serwist | OK | `main.py`, `marketpulse/next.config.ts` |
| (i) SW : `/api` en NetworkOnly ; logout purge IndexedDB + Cache Storage | OK | `marketpulse/src/app/sw.ts`, `src/lib/auth.tsx` |
| (j) Proxy Next : `experimental.proxyTimeout: 120000` | OK | `marketpulse/next.config.ts` |

## Risques résiduels

- Rate limit en mémoire, par processus : un redémarrage le remet à zéro.
- `JWT_SECRET` et mot de passe Postgres de développement présents dans `.env.example` : valeurs locales documentées, à changer avant tout hébergement réel de l'API.
- `COOKIE_SECURE=false` en HTTP local ; doit être `true` derrière HTTPS.
- Push web : `pywebpush` est dans `requirements.txt` (version épinglée), mais les clés VAPID ne sont pas configurées → notifications dans l'application uniquement ; l'envoi push réel n'a pas été testé.
- E-mail réel non configuré par défaut : sans compte d'envoi, le code arrive dans Mailpit (boîte de test) ou dans les logs de développement.
- Le mot de passe du compte d'envoi, une fois configuré, vit dans `.env` et dans l'environnement du conteneur (visible par `docker inspect` sur la machine).
- Google OAuth : jamais rejoué contre les serveurs Google.
- Pas de second facteur d'authentification.
- CSP du site : `unsafe-inline` (requis par Next) ; l'API répond `default-src 'none'`.
- FinBERT désactivé (trop lourd pour l'image) : sentiment des news toujours `NULL`.
- Anciens fichiers avec SQL concaténé : isolés dans `legacy/`, non importés par l'application.
