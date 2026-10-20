# ActuSUP — la veille des communicants

Site statique responsive conçu pour GitHub Pages. Le site affiche des articles provenant de flux RSS de médias francophones et ajoute un angle pédagogique sur leur intérêt pour les métiers de la communication.

## Fonctions
- Filtres par catégories et recherche textuelle.
- Résumé RSS, média d’origine, date et lien vers l’article.
- Angle « Pourquoi c’est important en communication ».
- Collecte programmée toutes les heures via GitHub Actions.
- Heure de la dernière collecte affichée en heure de Paris.
- Icônes de site, de signet mobile et manifeste web.

## Installation sur GitHub

1. Dépose tous les fichiers et dossiers du projet à la racine du dépôt, en conservant `.github/workflows/update-news.yml`.
2. Dans **Settings → Pages**, choisis **Deploy from a branch**, la branche `main` (ou ta branche par défaut) et le dossier `/ (root)`.
3. Dans **Settings → Actions → General**, vérifie que GitHub Actions est autorisé. Le workflow a été conçu sans `uses:` ni actions externes pour fonctionner avec les politiques qui interdisent les actions appartenant à d’autres dépôts.
4. Va dans l’onglet **Actions**, sélectionne **Actualiser ActuSUP**, puis **Run workflow** pour lancer la première collecte.
5. Une fois le workflow terminé, ouvre l’URL GitHub Pages du dépôt.

Pour un dépôt `username.github.io`, l’adresse du site est généralement `https://username.github.io/`. Pour un dépôt de projet, elle ressemble à `https://username.github.io/nom-du-depot/`.

## Actualisation automatique

Le workflow `.github/workflows/update-news.yml` démarre la collecte chaque heure à la minute 17 UTC. GitHub peut décaler les tâches programmées, notamment en période de forte charge. L’heure affichée correspond à la dernière collecte enregistrée, pas à une garantie que chaque média a publié à cet instant.

Le workflow utilise le `GITHUB_TOKEN` intégré et demande `contents: write` pour enregistrer le fichier `data/news.json` dans le dépôt. Dans **Settings → Actions → General → Workflow permissions**, il peut être nécessaire d’autoriser les permissions d’écriture si les paramètres du dépôt les restreignent. Aucune action externe `actions/checkout` ou `actions/setup-python` n’est utilisée.

Si tous les flux RSS sont indisponibles, le script conserve les dernières données connues. Les flux défaillants sont indiqués dans le fichier JSON et le site signale si la dernière collecte est ancienne.

## Sources configurées

- franceinfo — `https://www.francetvinfo.fr/titres.rss`
- France 24 — `https://www.france24.com/fr/rss`
- RFI — `https://www.rfi.fr/fr/rss`
- Le Monde — `https://www.lemonde.fr/rss/une.xml`
- Libération — `https://www.liberation.fr/arc/outboundfeeds/rss-all/?outputType=xml`
- Les Échos — `https://www.lesechos.fr/rss/rss_une.xml`
- Ouest-France — `https://www.ouest-france.fr/rss-en-continu.xml`
- Public Sénat — `https://www.publicsenat.fr/rss`
- LCP — `https://lcp.fr/rss.xml`

Les médias peuvent changer les adresses ou les conditions d’accès à leurs flux. Si un flux ne fonctionne plus, consulte les pages officielles du média et remplace l’URL dans `fetch_news.py`. La collecte ne contourne pas de paywall et ne récupère pas les articles complets.

## Catégorisation et limites

Les catégories sont attribuées automatiquement à partir de mots-clés dans les titres et les résumés RSS. Elles peuvent être imparfaites. L’angle communication est une explication pédagogique générée à partir de la catégorie, et non une analyse journalistique individualisée de chaque article. Vérifie les informations et consulte la source originale avant de les réutiliser.

L’agrégation RSS ne garantit pas qu’un sujet ait été traité simultanément dans la presse écrite, à la télévision et à la radio. Cette exigence du QCM de départ doit être vérifiée manuellement.

## Dépannage

- **Aucun article :** ouvre Actions, lance `Actualiser ActuSUP` et consulte les logs.
- **Le workflow n’apparaît pas :** vérifie le chemin exact `.github/workflows/update-news.yml` sur la branche par défaut.
- **Le push échoue pour manque de permission :** vérifie `Settings → Actions → General → Workflow permissions` et autorise l’accès en écriture au contenu si tu es autorisé à le faire.
- **Une source est en erreur :** son flux a peut-être changé ou bloque les requêtes automatisées ; la collecte des autres sources continue.
