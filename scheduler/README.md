# Déclencheur externe ActuSUP (Cloudflare Workers)

Ce Worker fournit un deuxième planificateur indépendant de GitHub Actions. Il appelle le workflow `Actualiser ActuSUP` toutes les dix minutes, même lorsque le planificateur natif GitHub ne lance plus ses événements `schedule`.

Le Worker ne collecte pas les flux RSS lui-même : il déclenche le workflow Python existant. Le fonctionnement du site et son design ne sont pas modifiés.

## 1. Créer un jeton GitHub à portée limitée

Depuis le compte qui possède `sopp24/ActuSUP`, crée un **Fine-grained personal access token** :

- Repository access : `Only select repositories` → `ActuSUP`.
- Repository permissions : `Actions` → `Read and write`.
- Aucun droit `Contents` n'est nécessaire pour déclencher le workflow.

Le jeton permet de lancer les workflows du dépôt. Ne le publie jamais dans le dépôt, dans une issue ou dans une conversation.

Page de création : https://github.com/settings/personal-access-tokens/new

## 2. Déployer le Worker Cloudflare

Un compte Cloudflare avec Workers activé suffit. Aucun nom de domaine n'est nécessaire.

Depuis un terminal avec Node.js installé :

```bash
npm install -g wrangler
npx wrangler login
cd scheduler
npx wrangler secret put GITHUB_TOKEN
```

À l'invite, colle le jeton GitHub créé à l'étape 1. La valeur est enregistrée comme secret Cloudflare et n'est pas écrite dans ce dépôt.

Déploie ensuite le Worker :

```bash
npx wrangler deploy
```

Le fichier `wrangler.toml` configure automatiquement un déclenchement toutes les dix minutes (minutes 09, 19, 29, 39, 49 et 59, en UTC).

## 3. Comportement anti-doublon et récupération

À chaque déclenchement, le Worker :

1. consulte les dix dernières exécutions du workflow GitHub ;
2. ne fait rien si une collecte est déjà en cours ;
3. annule une exécution active qui dépasse douze minutes ;
4. ne déclenche rien si une collecte vient de réussir depuis moins de huit minutes ;
5. sinon, lance `workflow_dispatch` sur `main`.

Le cron natif GitHub reste en place comme deuxième mécanisme. Le Worker ne crée donc pas une seconde collecte quand le cron GitHub vient de réussir.

## 4. Vérifier le fonctionnement

Dans Cloudflare Dashboard → Workers & Pages → `actusup-external-scheduler` → Logs, les événements attendus sont :

- `workflow_dispatch` : le Worker a lancé une collecte ;
- `recent_success` : le cron GitHub avait déjà réussi, donc pas de doublon ;
- `collection_already_active` : une collecte est déjà en cours ;
- une erreur GitHub API : vérifier l'expiration du jeton et le droit `Actions: Read and write`.

Dans GitHub → Actions → `Actualiser ActuSUP`, les exécutions déclenchées par le Worker apparaissent comme `workflow_dispatch`.

## Pourquoi cette deuxième horloge ?

Le cron GitHub reste utile, mais GitHub documente que ses événements planifiés peuvent être retardés ou abandonnés et qu'un workflow planifié peut cesser de se déclencher alors que les lancements manuels fonctionnent. Un Cron Trigger Cloudflare indépendant évite de dépendre d'une seule horloge. Le plan Workers Free autorise jusqu'à cinq Cron Triggers par compte et 100 000 requêtes par jour ; cette configuration n'en utilise qu'un et le déclenche 144 fois par jour.

Documentation :
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://developers.cloudflare.com/workers/platform/limits/
- https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event
