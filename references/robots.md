# Robots : qui est qui, comment les vérifier, comment les gérer

## Sommaire
1. Les familles et ce qu'elles valent
2. Table des robots
3. Vérifier un robot
4. Recettes robots.txt
5. Bloquer ou ralentir au niveau du serveur

## 1. Les familles et ce qu'elles valent

| Famille | Ce que fait le robot | Ce que ça rapporte | Décision type |
|---|---|---|---|
| moteur | Explore et indexe pour les résultats classiques (et les réponses IA de Google et Bing) | Trafic organique | Toujours autoriser, surveiller le budget |
| ia-recherche | Construit l'index d'un moteur IA (ChatGPT Search, Perplexity, Claude) | Être cité et recevoir des clics depuis les réponses IA | Autoriser si l'on veut être cité |
| ia-utilisateur | Ouvre une page parce qu'un utilisateur l'a demandée à un assistant, à l'instant | Le meilleur signal GEO : la page sert de source à une réponse | Autoriser ; ces robots agissent pour un humain et ne suivent pas toujours robots.txt |
| ia-entrainement | Collecte pour entraîner des modèles | Aucune visite directe ; présence à long terme dans les connaissances du modèle | Choix stratégique : autoriser, limiter ou bloquer |
| outil-seo | Construit les index de liens des outils (Ahrefs, Semrush, Majestic…) | Votre visibilité dans ces outils, rien côté moteurs | Limiter si la charge est forte |
| apercu | Récupère titre et image quand un lien est partagé | Aperçus soignés sur les réseaux | Autoriser |

Point clé : bloquer GPTBot (entraînement) n'empêche pas ChatGPT de vous citer, car c'est OAI-SearchBot qui alimente ChatGPT Search. Même logique chez Anthropic (ClaudeBot, Claude-SearchBot, Claude-User) et chez Perplexity (PerplexityBot, Perplexity-User). Chez Google, il n'existe pas de robot IA séparé : `Google-Extended` est seulement un jeton robots.txt qui règle l'usage des pages pour Gemini, sans changer l'exploration par Googlebot ni la présence dans les AI Overviews. `Applebot-Extended` joue le même rôle chez Apple.

## 2. Table des robots

| Robot (user-agent) | Éditeur | Famille | Jeton robots.txt | Vérification |
|---|---|---|---|---|
| Googlebot (+ Image, Video, News, Storebot, InspectionTool, GoogleOther, AdsBot) | Google | moteur | Googlebot, Googlebot-Image… | Liste d'IP officielle ou DNS (googlebot.com, google.com, googleusercontent.com) |
| Google-CloudVertexBot | Google | ia-entrainement | Google-CloudVertexBot | Listes d'IP de Google |
| bingbot | Microsoft | moteur | bingbot | Liste d'IP officielle ou DNS (search.msn.com) |
| YandexBot | Yandex | moteur | Yandex | DNS (yandex.ru, .net, .com) |
| Baiduspider | Baidu | moteur | Baiduspider | DNS (baidu.com, baidu.jp) |
| Applebot | Apple | moteur | Applebot (+ Applebot-Extended pour l'IA) | DNS (applebot.apple.com) |
| DuckDuckBot, Qwantbot, SeznamBot, PetalBot | divers | moteur | leur nom | selon l'éditeur |
| OAI-SearchBot | OpenAI | ia-recherche | OAI-SearchBot | openai.com/searchbot.json |
| ChatGPT-User | OpenAI | ia-utilisateur | ChatGPT-User | openai.com/chatgpt-user.json |
| GPTBot | OpenAI | ia-entrainement | GPTBot | openai.com/gptbot.json |
| PerplexityBot | Perplexity | ia-recherche | PerplexityBot | perplexity.ai/perplexitybot.json |
| Perplexity-User | Perplexity | ia-utilisateur | Perplexity-User | perplexity.ai/perplexity-user.json |
| Claude-SearchBot | Anthropic | ia-recherche | Claude-SearchBot | non exploitée par le script : juger au comportement |
| Claude-User | Anthropic | ia-utilisateur | Claude-User | idem |
| ClaudeBot | Anthropic | ia-entrainement | ClaudeBot | idem |
| MistralAI-User | Mistral | ia-utilisateur | MistralAI-User | aucune |
| DuckAssistBot | DuckDuckGo | ia-utilisateur | DuckAssistBot | aucune |
| meta-externalagent, meta-externalfetcher | Meta | ia-entrainement, ia-utilisateur | meta-externalagent | aucune |
| Amazonbot, Bytespider, CCBot, cohere-ai, Diffbot, AI2Bot | divers | ia-entrainement | leur nom | aucune (Bytespider ignore souvent robots.txt) |
| AhrefsBot, SemrushBot, MJ12bot, DotBot, BLEXBot, DataForSeoBot, SEOkicks, Barkrowler | outils | outil-seo | leur nom | inutile en pratique |
| facebookexternalhit, Twitterbot, LinkedInBot, Slackbot, Discordbot, TelegramBot, WhatsApp | réseaux | apercu | leur nom | inutile en pratique |

Les noms évoluent : quand un user-agent inconnu revient souvent dans « Autres robots », chercher sa page officielle et l'ajouter à la liste `BOTS` du script (motif, nom, famille, jeton, vérification).

## 3. Vérifier un robot

Un user-agent se copie en une ligne : sur un site moyen, une part notable des « Googlebot » et des « ChatGPT-User » sont faux (sondes de sécurité, scrapers). Deux méthodes fiables :

- **Liste d'IP officielle** (Google, Bing, OpenAI, Perplexity) : l'IP doit appartenir à l'un des blocs publiés. C'est la méthode utilisée par `--verify`.
- **DNS inverse confirmé** (Google, Bing, Apple, Yandex, Baidu) : `host <ip>` doit donner un nom du domaine de l'éditeur, et ce nom doit pointer à nouveau vers la même IP. Le script le fait pour les `--dns-limit` IP les plus actives de chaque robot.

Sans méthode publiée (Anthropic, Meta, Amazon…), juger au comportement : un robot IA qui demande surtout des adresses en 404 ou des chemins comme `/.env` est presque toujours un imposteur.

Derrière un CDN (Cloudflare ou autre), l'IP du journal est celle du CDN : toute vérification est fausse tant que le serveur n'enregistre pas l'IP réelle (module `real_ip` de nginx avec l'en-tête du CDN, ou `mod_remoteip` d'Apache).

## 4. Recettes robots.txt

Être cité par les IA sans nourrir leur entraînement :

```
User-agent: GPTBot
User-agent: ClaudeBot
User-agent: CCBot
User-agent: Bytespider
User-agent: meta-externalagent
User-agent: Google-Extended
User-agent: Applebot-Extended
Disallow: /

User-agent: OAI-SearchBot
User-agent: Claude-SearchBot
User-agent: PerplexityBot
Allow: /
```

Ralentir les outils SEO sans les couper (Crawl-delay est respecté par Ahrefs, Semrush et Majestic, mais ignoré par Googlebot) :

```
User-agent: AhrefsBot
User-agent: SemrushBot
User-agent: MJ12bot
Crawl-delay: 5
```

Ne jamais bloquer dans robots.txt une adresse qu'on veut désindexer : Google ne verrait plus la balise noindex. robots.txt règle l'exploration, pas l'indexation.

## 5. Bloquer ou ralentir au niveau du serveur

robots.txt est une demande polie. Pour les robots qui l'ignorent (section « interdits mais demandés » du rapport) et pour les faux robots, agir dans nginx ou Apache :

- user-agent indésirable : une `map` nginx sur `$http_user_agent` qui renvoie 403 ;
- faux moteurs : bloquer par IP les adresses listées par le rapport, ou limiter le débit (`limit_req`) des requêtes qui se disent Googlebot sans venir des blocs de Google ;
- sondes de sécurité : un 403 ou un 404 sec suffit ; fail2ban sur ces motifs coupe les scanners récurrents.

Toujours tester (`nginx -t`) et laisser Googlebot vérifié hors de toute limitation.
