---
name: logbot
description: Analyse les journaux serveur (access.log nginx ou Apache, fichiers .gz compris) du point de vue SEO et GEO avec un script fourni. Couvre les moteurs (Googlebot, Bingbot…), les robots IA d'entraînement, de recherche et de lecture à la demande (GPTBot, OAI-SearchBot, ChatGPT-User, ClaudeBot, PerplexityBot…), les faux robots, le budget de crawl et son gaspillage, la couverture du sitemap, les pages lues par les IA et les robots qui ignorent robots.txt. À utiliser dès que l'utilisateur parle de logs, de journaux d'accès, de crawl, de budget de crawl, de passage de Googlebot, de « qui crawle mon site », de robots IA, de sa visibilité dans ChatGPT ou Perplexity vue côté serveur, de faux Googlebot ou de charge serveur due aux robots, même s'il ne dit pas « analyse de logs ».
---

# Analyse de journaux SEO et GEO

Les journaux du serveur sont la seule source qui dit ce que les robots font vraiment : quelles pages Googlebot visite et à quel rythme, ce qu'il gaspille, quels robots IA lisent le site et pourquoi, lesquels sont des imposteurs. La Search Console n'en donne qu'un résumé, et rien sur les IA. Ce skill transforme des journaux bruts en décisions.

Le travail se fait en quatre temps : réunir les journaux, lancer le script, interpréter avec la grille ci-dessous, rendre un rapport d'actions.

## 1. Réunir les journaux

- **Où** : nginx `/var/log/nginx/*access.log*`, Apache `/var/log/apache2/` ou `/var/log/httpd/`, hébergement mutualisé : rubrique « logs bruts » ou « raw access » du panneau. Prendre aussi les fichiers tournés (`.1`, `.gz`).
- **Combien** : 30 jours au moins pour le budget de crawl et la couverture du sitemap, car Googlebot ne revoit pas tout chaque semaine. 7 jours suffisent pour les robots IA et les faux robots.
- **Format** : le format « combined », celui par défaut de nginx et d'Apache. Si beaucoup de lignes sont « illisibles », montrer une ligne à l'utilisateur et adapter `LINE_RE` dans le script.
- **CDN** : derrière Cloudflare ou un autre CDN, les IP du journal sont celles du CDN, ce qui fausse toute vérification de robot, et les pages servies depuis le cache n'apparaissent pas. Le signaler et demander les journaux du CDN ou la configuration de l'IP réelle.
- **Données personnelles** : les IP sont des données personnelles. Lancer le script là où sont les journaux (serveur ou poste de l'utilisateur) et ne travailler que sur le rapport agrégé ; ne pas recopier de journaux bruts dans la conversation au-delà de quelques lignes d'exemple.

## 2. Lancer le script

`scripts/logbot.py` : Python 3.8 ou plus, bibliothèque standard seulement. Il lit les fichiers au fil de l'eau, donc plusieurs centaines de Mo ne posent pas de problème.

```bash
python3 scripts/logbot.py /var/log/nginx/access.log* --days 30 --verify \
  --sitemap https://exemple.fr/sitemap.xml --robots https://exemple.fr/robots.txt --out rapport-logs
```

| Option | Rôle |
|---|---|
| `--days N` | ne garder que les N derniers jours |
| `--verify` | démasquer les faux robots : listes d'IP officielles (Google, Bing, OpenAI, Perplexity) et DNS inverse confirmé (Apple, Yandex, Baidu). À mettre presque toujours |
| `--dns-limit N` | nombre d'IP vérifiées par DNS pour chaque robot sans liste officielle (100 par défaut) |
| `--sitemap` | URL ou fichier du sitemap (index compris) : adresses jamais vues par Googlebot, crawl hors sitemap |
| `--robots` | URL ou fichier robots.txt : robots qui demandent des adresses interdites |
| `--top N` | longueur des classements |
| `--out DIR` | écrit `rapport.md` et `adresses.csv` (une ligne par adresse, un robot par colonne) au lieu de la sortie standard |

Ordre de grandeur : 300 000 lignes avec `--verify` et le sitemap prennent environ une minute et demie. Sur un serveur distant, le script se lance sans y être copié : `ssh serveur "python3 - /var/log/nginx/access.log* --days 30 --verify" < scripts/logbot.py`.

## 3. Interpréter : la grille

Le rapport donne des chiffres ; la valeur ajoutée, c'est de dire ce qu'ils signifient pour ce site-là. Lire les sections dans cet ordre.

**Vérification** (en-tête et section 3). Sans `--verify`, prévenir que tous les chiffres incluent des imposteurs. Avec, les faux robots sont sortis de leur famille d'origine : citer leur volume et leur comportement, souvent des sondes comme `/.env`. Une colonne « Non vérifié » élevée pour un moteur veut dire que `--dns-limit` est trop bas ; pour un robot IA sans liste officielle, juger au taux de 4xx et aux sondes.

**Qui consomme le serveur** (section 1). Comparer la part des moteurs à celle des outils SEO, des IA d'entraînement et des scripts. Quand les outils SEO ou les IA d'entraînement pèsent plus que les moteurs, c'est de la charge sans retour : proposer Crawl-delay, robots.txt ou une limitation serveur (voir `references/robots.md`). Les « navigateurs » contiennent aussi des robots déguisés : ne pas les présenter comme du trafic humain certain.

**Budget de crawl de Googlebot** (section 4), le cœur de l'analyse SEO :
- *Gaspillage certain* au-dessus d'environ 10 % : à traiter. Redirections : chercher les liens internes qui pointent vers des adresses redirigées, et les passages http vers https ou avec et sans www. 4xx : liens internes cassés, ou anciennes adresses encore liées depuis l'extérieur, à rediriger si elles ont de la valeur. Paramètres de pistage ou de session : à retirer des liens internes.
- *Paramètres* hors pistage (tri, filtres, pagination) : ce n'est pas forcément du gaspillage, car sur un site en PHP `?id=` est souvent l'adresse normale. Regarder les gabarits pour repérer les facettes et les tris qui multiplient les adresses, puis proposer canonical, liens internes retirés ou règles de robots.txt.
- *Gabarits* : les types de pages où part le crawl. Les confronter aux pages qui comptent pour l'activité. Des profils, des tags ou des pages de tri en tête, avec les articles ou les fiches produit loin derrière, signalent un maillage ou une architecture à corriger.
- *Fréquence* : beaucoup de pages vues une seule fois en 30 jours, c'est normal pour des archives, inquiétant pour des pages stratégiques.

**Sitemap** (section 5). Rapporter la couverture à la durée analysée : sur 7 jours, 6 % est banal ; sur 30 jours, moins de la moitié des pages importantes vues est un vrai problème (pages trop profondes, peu liées, ou jugées sans intérêt). Les adresses crawlées hors sitemap sont soit oubliées du sitemap (à ajouter si elles doivent être indexées), soit parasites (à fermer).

**GEO : ce que lisent les IA** (section 6). Distinguer les trois familles, c'est l'essentiel de l'analyse GEO :
- *Lecture à la demande* (ChatGPT-User, Claude-User, Perplexity-User…) : une IA a ouvert la page à l'instant pour répondre à quelqu'un. C'est le meilleur indice, côté serveur, qu'une page sert de source. Lister ces pages : ce sont les « pages sources » du site, à tenir à jour et à structurer pour être reprises (réponse d'abord, faits datés, chiffres sourcés). Des 4xx dans cette famille, quand les robots sont authentiques, montrent des liens morts que les IA continuent de citer : rediriger.
- *Index de recherche* (OAI-SearchBot, PerplexityBot, Claude-SearchBot) : la condition pour être cité dans ChatGPT Search, Perplexity ou Claude. Absents ou bloqués, le site ne peut pas être cité par ces moteurs.
- *Entraînement* (GPTBot, ClaudeBot, Bytespider…) : aucun trafic direct. Les laisser passer ou non est un choix ; rappeler que bloquer GPTBot ne bloque pas OAI-SearchBot.
Les gabarits lus par les IA révèlent parfois des surprises (générateurs d'images, pages de partage, profils) : signaler ce qui consomme sans rien apporter.

**robots.txt** (section 7). Un robot qui demande des adresses interdites ignore robots.txt : seul un blocage serveur l'arrêtera. Vérifier d'abord que l'interdiction est voulue.

**Fichiers techniques** (section 8). Des robots.txt et sitemap très demandés, c'est normal. Pour `llms.txt`, dire combien de requêtes et de qui ; à ce jour, aucun grand assistant n'a documenté son usage, donc ne pas le présenter comme un levier prouvé.

**Sondes** (section 9). Ce n'est pas du SEO, mais le volume dit si le serveur est la cible de scanners. Ces requêtes sont déjà exclues des classements ; renvoyer vers un blocage serveur si le volume est fort.

## 4. Rendre le rapport

Répondre dans la langue de l'utilisateur, avec cette structure :

```markdown
# Analyse des journaux : <site>, <période>

## En bref
3 à 5 phrases : le constat principal SEO, le constat principal GEO, le gaspillage ou le risque le plus coûteux.

## Ce que disent les journaux
Les chiffres qui comptent, chacun suivi de son interprétation (jamais un tableau recopié sans commentaire).

## Actions prioritaires
| Priorité | Action | Pourquoi (chiffre du rapport) | Effort |
Du plus rentable au moins rentable : 5 à 8 actions concrètes (fichier, règle ou page à modifier).

## Limites de l'analyse
Période, vérification faite ou non, CDN, journaux partiels, robots invérifiables.
```

Joindre ou citer `adresses.csv` quand l'utilisateur veut descendre page par page (tri par robot, pages jamais vues par Googlebot, etc.).

## Pièges à éviter

- Conclure sur 2 ou 3 jours de journaux : le crawl varie fortement d'un jour à l'autre.
- Prendre le user-agent pour une preuve : sans vérification, une part des « Googlebot » et des robots IA sont faux.
- Bloquer un vrai Googlebot par erreur : ne jamais limiter les IP vérifiées de Google.
- Confondre exploration et indexation : une page servie en 200 à Googlebot n'est pas forcément indexée.
- Oublier les serveurs multiples : derrière un répartiteur de charge, réunir les journaux de chaque serveur.

Pour la liste des robots, leurs jetons robots.txt, les méthodes de vérification et les recettes de blocage : `references/robots.md`.
