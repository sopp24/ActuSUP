# ActuSUP — la veille des communicants

Site statique responsive conçu pour GitHub Pages. Le site affiche des articles provenant de flux RSS de médias francophones et ajoute un angle pédagogique sur leur intérêt pour les métiers de la communication.

## Fonctions
- Filtres par catégories et recherche textuelle.
- Tri des articles par date ou par média et affichage progressif.
- Résumé RSS, média d’origine, date et lien vers l’article.
- Angle « Pourquoi c’est important en communication ».
- Baromètre des 20 sujets les plus couverts sur les sept derniers jours.
- Collecte automatique en chaîne toutes les dix minutes via GitHub Actions, avec lancement manuel possible.
- Heure de la dernière collecte affichée en heure de Paris.
- Icônes de site, de signet mobile et manifeste web.

## Installation sur GitHub

1. Dépose tous les fichiers et dossiers du projet à la racine du dépôt, en conservant `.github/workflows/update-news.yml`.
2. Dans **Settings → Pages**, choisis **Deploy from a branch**, la branche `main` (ou ta branche par défaut) et le dossier `/ (root)`.
3. Dans **Settings → Actions → General**, vérifie que GitHub Actions est autorisé. Le workflow a été conçu sans `uses:` ni actions externes pour fonctionner avec les politiques qui interdisent les actions appartenant à d’autres dépôts.
4. Va dans l’onglet **Actions**, sélectionne **Actualiser ActuSUP**, puis **Run workflow** pour lancer une collecte manuelle.
5. Une fois le workflow terminé, ouvre l’URL GitHub Pages du dépôt.

Pour un dépôt `username.github.io`, l’adresse du site est généralement `https://username.github.io/`. Pour un dépôt de projet, elle ressemble à `https://username.github.io/nom-du-depot/`.

## Actualisation automatique

Le collecteur utilise une **chaîne de workflows GitHub Actions auto-déclenchée toutes les dix minutes**. Il ne dépend plus du planificateur `schedule` de GitHub, qui avait cessé d'émettre les événements attendus.

Le fonctionnement est le suivant :

1. Un changement ciblé sur `main` (`fetch_news.py`, `requirements.txt` ou le workflow) ou un lancement manuel démarre le premier cycle.
2. Le workflow collecte les flux RSS, régénère `data/news.json` et publie les données.
3. Il attend le temps restant pour atteindre dix minutes depuis le début du cycle, puis déclenche sa prochaine exécution avec l'API `workflow_dispatch` et le `GITHUB_TOKEN` du dépôt.
4. Le watchdog, déclenché à la fin de chaque exécution, relance les échecs. Après trois tentatives infructueuses, il ouvre un nouveau cycle après cinq minutes.

Le jeton intégré dispose de `actions: write` pour créer la prochaine exécution et de `contents: write` pour publier `data/news.json`. GitHub autorise explicitement `workflow_dispatch` avec le `GITHUB_TOKEN`. Aucun secret externe, compte Cloudflare ou service de planification tiers n'est nécessaire.

Le délai visé est de dix minutes entre deux débuts de collecte. Le démarrage réel peut toutefois être légèrement retardé si les runners GitHub sont en attente dans une file.

Le bouton **Actualiser** du site recharge le fichier de données déjà publié ; il ne lance pas de collecte RSS. Seule une exécution du workflow récupère de nouveaux articles.

Si tous les flux RSS sont indisponibles, les dernières données connues sont conservées. Si seuls certains flux échouent, les articles déjà récupérés de ces médias sont conservés pendant 30 jours, le temps que leur flux redevienne disponible. Les erreurs sont indiquées dans le fichier JSON et le site signale si la dernière collecte est ancienne.

## Sources configurées

- franceinfo — `https://www.francetvinfo.fr/titres.rss`
- France 24 — `https://www.france24.com/fr/rss`
- RFI — `https://www.rfi.fr/fr/rss`
- Le Monde — `https://www.lemonde.fr/rss/une.xml`
- Le Figaro — `https://www.lefigaro.fr/rss/figaro_actualites.xml`
- BFMTV — `https://www.bfmtv.com/rss/news-24-7/`
- 20 Minutes — `https://www.20minutes.fr/feeds/rss-une.xml`
- Actu.fr — `https://actu.fr/rss.xml`
- Courrier International — `https://www.courrierinternational.com/feed/all/rss.xml`
- Euronews — `https://fr.euronews.com/rss`
- La Croix – International — `https://www.la-croix.com/feeds/rss/international.xml`
- Libération — `https://www.liberation.fr/arc/outboundfeeds/rss-all/?outputType=xml`
- Les Échos — `https://www.lesechos.fr/rss/rss_une.xml`
- Ouest-France — `https://www.ouest-france.fr/rss-en-continu.xml`
- Public Sénat — `https://www.publicsenat.fr/rss`
- LCP — `https://lcp.fr/rss.xml`
- CB News — `https://www.cbnews.fr/rss.xml`
- Creapills — `https://creapills.com/feed`
- INA – La Revue des médias — `https://larevuedesmedias.ina.fr/rss/all`
- Next.ink — `https://next.ink/feed/`
- Le Monde Informatique — `https://www.lemondeinformatique.fr/flux-rss/thematique/toutes-les-actualites/rss.xml`
- Futura — `https://www.futura-sciences.com/rss/actualites.xml`
- Reporterre — `https://reporterre.net/spip.php?page=backend-simple`
- Télérama — `https://www.telerama.fr/rss/latest-articles.xml`

Les médias peuvent changer les adresses ou les conditions d’accès à leurs flux. Si un flux ne fonctionne plus, consulte les pages officielles du média et remplace l’URL dans `fetch_news.py`. La collecte ne contourne pas de paywall et ne récupère pas les articles complets.

## Catégorisation et limites

Les catégories et les angles de communication sont attribués automatiquement à partir de mots-clés dans les titres et les résumés RSS. La détection s’effectue sur des mots ou expressions entiers afin d’éviter les faux positifs dus à de simples sous-chaînes. Elle peut néanmoins rester imparfaite. L’angle communication est une explication pédagogique générée à partir du titre, du résumé et de la catégorie, et non une analyse journalistique individualisée de chaque article. Vérifie les informations et consulte la source originale avant de les réutiliser.

L’agrégation RSS ne garantit pas qu’un sujet ait été traité simultanément dans la presse écrite, à la télévision et à la radio. Cette exigence du QCM de départ doit être vérifiée manuellement.

## Dépannage

- **Aucune actualisation automatique :** vérifie l'historique GitHub Actions et cherche le dernier événement `workflow_dispatch`. Un échec de la requête de chaînage apparaît dans les journaux du collecteur.
- **Le workflow n’apparaît pas :** vérifie le chemin exact `.github/workflows/update-news.yml` sur la branche par défaut.
- **Le push échoue pour manque de permission :** vérifie `Settings → Actions → General → Workflow permissions` et autorise l’accès en écriture au contenu si tu es autorisé à le faire.
- **Une source est en erreur :** son flux a peut-être changé ou bloque les requêtes automatisées ; la collecte des autres sources continue et les derniers articles de la source en erreur sont temporairement conservés.
