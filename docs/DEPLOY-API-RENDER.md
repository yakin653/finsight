# Déployer l'API sur Render + Neon (gratuit) et la brancher sur Vercel

Objectif : le lien public https://marketpulse-zeta-jet.vercel.app devient la
vraie plateforme (comptes, alertes, chat, données Yahoo). Le navigateur parle
toujours à `/api` sur le site ; Vercel relaie vers l'API Render via la
variable `API_PROXY_TARGET` (déjà prévue dans `next.config.ts`). Aucun
changement de code n'est nécessaire.

Architecture cible : Vercel (site) → Render (FastAPI) → Neon (PostgreSQL).
Ollama reste local : sur Render, le chat répond par le texte déterministe
Python (comportement prévu, réponses exactes mais sans reformulation).

## Étape 0 — Pousser le code à jour (obligatoire)

Render déploie depuis GitHub : le backend actuel doit d'abord être commité
(c'est aussi le défaut bloquant relevé par l'audit Phase V).

```powershell
cd C:\Users\yakin\finsight
git add -A
git commit -m "Backend MarketPulse actuel + config Render"
git push

cd C:\Users\yakin\marketpulse
git add -A
git commit -m "Nettoyage Phase V (fichiers morts, docs, gitignore sw.js)"
git push
```

## Étape 1 — Base PostgreSQL Neon (gratuite, sans expiration)

1. Créer un compte sur https://neon.tech, puis un projet `marketpulse`.
2. Dans « Connection string », copier la chaîne (format `postgresql://...`).
3. La transformer avant de la coller dans Render : remplacer le début
   `postgresql://` par `postgresql+psycopg://` et conserver la fin
   (`?sslmode=require`). Exemple de forme finale :
   `postgresql+psycopg://USER:MOTDEPASSE@HOST/neondb?sslmode=require`

Si le projet Neon a déjà été relié à ce dépôt, la chaîne déjà transformée est dans
`.env` (ignoré par Git) sous le nom `NEON_DATABASE_URL`. Ce nom est volontairement
distinct : en local, `DATABASE_URL` reste la base PostgreSQL de `docker-compose.yml`
et rien ne lit `NEON_DATABASE_URL`. Sur Render, la variable s'appelle `DATABASE_URL`.

## Étape 2 — Service API sur Render

1. Créer un compte sur https://render.com (connexion GitHub conseillée).
2. « New » → « Blueprint » → choisir le dépôt `finsight` : Render lit
   `render.yaml` à la racine.
3. Quand `DATABASE_URL` est demandée (sync: false), coller la chaîne Neon
   transformée de l'étape 1 (la valeur de `NEON_DATABASE_URL` dans `.env`).
4. « Apply » / « Create ». Le premier build prend plusieurs minutes
   (numpy, scikit-learn). Vérifier ensuite :
   https://marketpulse-api.onrender.com/health → `{"status":"ok",...}`
   (si le nom `marketpulse-api` est pris, Render en suffixe un autre ;
   noter l'URL réelle, elle sert à l'étape 3).
5. Au premier démarrage, les tables sont créées et les 5 symboles de base
   (AAPL, MSFT, TSLA, NVDA, BTC-USD) sont chargés depuis Yahoo.

Variables déjà posées par `render.yaml` : JWT_SECRET (généré par Render),
CORS_ORIGINS (le site public + localhost), APP_PUBLIC_URL (le lien public,
pour que les liens de réinitialisation pointent sur le site),
COOKIE_SECURE=true, KNOWLEDGE_DIR, MARKET_REFRESH_ON_START=1.

## Étape 3 — Brancher Vercel sur l'API

1. Vercel → projet `marketpulse` → Settings → Environment Variables.
2. Ajouter (Production) : `API_PROXY_TARGET` = l'URL Render de l'étape 2,
   sans slash final, par exemple `https://marketpulse-api.onrender.com`.
3. Deployments → « Redeploy » (les rewrites sont figés au build : le
   redéploiement est indispensable).

## Étape 4 — Vérifier sur le lien public

Sur https://marketpulse-zeta-jet.vercel.app :

1. `/register` : créer un compte (il arrive dans Neon).
2. Connexion avec ce compte → dashboard avec les vrais cours.
3. `/alerts` : créer puis supprimer une alerte (CRUD via l'API).
4. `/chat` : poser « Quel est le prix de AAPL ? » (réponse du repli Python).
5. `/status` : API et base doivent être OK.

## Mot de passe oublié sur le public

Sans serveur mail, aucun e-mail ne peut partir (APP_ENV=production n'écrit
pas le lien dans les logs). Deux options :

- **Lire le lien dans les logs Render** (suffisant pour une soutenance) :
  ajouter temporairement la variable `DEV_LOG_RESET_LINKS=true` dans
  Render, redémarrer le service, faire une demande, lire le lien dans
  « Logs », puis retirer la variable.
- **Vrai e-mail** : créer un compte SMTP gratuit (par exemple Brevo),
  puis définir dans Render : SMTP_HOST, SMTP_PORT=587, SMTP_USER,
  SMTP_PASSWORD, SMTP_FROM.

## Limites gratuites à connaître

- Render gratuit : le service s'endort après ~15 minutes sans trafic ;
  le premier appel ensuite prend jusqu'à ~1 minute (écran de réveil).
  Pour la soutenance, ouvrir `/health` quelques minutes avant.
- Neon gratuit : la base reste (pas d'expiration à 30 jours comme
  l'ancien Postgres gratuit de Render), quotas larges pour ce projet.
- Pas d'Ollama là-bas : chat = texte déterministe, Pulse Score inchangé
  (calculé dans le navigateur), aucune donnée inventée.
