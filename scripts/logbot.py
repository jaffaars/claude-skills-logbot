#!/usr/bin/env python3
"""logbot.py : journaux nginx / Apache lus du point de vue SEO et GEO.

Classe chaque requete par robot (moteurs, IA d'entrainement, IA de recherche, IA a la demande
d'un utilisateur, outils SEO, apercus sociaux), demasque les faux robots (listes d'IP officielles
et DNS), mesure le budget de crawl et son gaspillage, regroupe les adresses par gabarit et sort
un rapport Markdown plus un CSV par adresse. Python 3.8+, bibliotheque standard seulement.

Exemples :
  python3 logbot.py /var/log/nginx/access.log*
  python3 logbot.py access.log*.gz --days 30 --verify --sitemap https://exemple.fr/sitemap.xml
  python3 logbot.py logs/*.gz --robots https://exemple.fr/robots.txt --out rapport
"""

import argparse
import collections
import csv
import datetime as dt
import gzip
import io
import ipaddress
import json
import os
import re
import socket
import sys
import urllib.parse
import urllib.request
import urllib.robotparser
import xml.etree.ElementTree as ET

UA_TOOL = "logbot/1.0 (+https://github.com/jaffaars/claude-skills-logbot)"

# --- Robots connus -------------------------------------------------------------------------
# (motif du user-agent, nom, famille, jeton robots.txt, verification)
# Familles : moteur, ia-recherche, ia-utilisateur, ia-entrainement, outil-seo, apercu.
# Verification : "ip:<cle>" = liste d'IP officielle (IP_LISTS), "dns:<domaines>" = DNS inverse confirme.
# Le premier motif qui correspond gagne : les plus precis sont en tete.
G_DNS = "dns:googlebot.com,google.com,googleusercontent.com"
BOTS = [
    (r"Googlebot-Image", "Googlebot-Image", "moteur", "Googlebot-Image", "ip:google"),
    (r"Googlebot-Video", "Googlebot-Video", "moteur", "Googlebot-Video", "ip:google"),
    (r"Googlebot-News", "Googlebot-News", "moteur", "Googlebot-News", "ip:google"),
    (r"Storebot-Google", "Storebot-Google", "moteur", "Storebot-Google", "ip:google"),
    (r"Google-InspectionTool", "Google-InspectionTool", "moteur", "Googlebot", "ip:google"),
    (r"GoogleOther", "GoogleOther", "moteur", "GoogleOther", "ip:google"),
    (r"Google-CloudVertexBot", "Google-CloudVertexBot", "ia-entrainement", "Google-CloudVertexBot", "ip:google"),
    (r"AdsBot-Google", "AdsBot-Google", "moteur", "AdsBot-Google", "ip:google"),
    (r"Googlebot", "Googlebot", "moteur", "Googlebot", "ip:google"),
    (r"bingbot|BingPreview", "Bingbot", "moteur", "bingbot", "ip:bing"),
    (r"YandexBot|YandexImages", "YandexBot", "moteur", "Yandex", "dns:yandex.ru,yandex.net,yandex.com"),
    (r"Baiduspider", "Baiduspider", "moteur", "Baiduspider", "dns:baidu.com,baidu.jp"),
    (r"DuckDuckBot", "DuckDuckBot", "moteur", "DuckDuckBot", ""),
    (r"Qwantbot|Qwantify", "Qwantbot", "moteur", "Qwantbot", ""),
    (r"SeznamBot", "SeznamBot", "moteur", "SeznamBot", ""),
    (r"Applebot", "Applebot", "moteur", "Applebot", "dns:applebot.apple.com"),
    (r"PetalBot", "PetalBot", "moteur", "PetalBot", ""),
    (r"OAI-SearchBot", "OAI-SearchBot", "ia-recherche", "OAI-SearchBot", "ip:openai-search"),
    (r"ChatGPT-User", "ChatGPT-User", "ia-utilisateur", "ChatGPT-User", "ip:openai-user"),
    (r"GPTBot", "GPTBot", "ia-entrainement", "GPTBot", "ip:openai-gptbot"),
    (r"Claude-SearchBot", "Claude-SearchBot", "ia-recherche", "Claude-SearchBot", ""),
    (r"Claude-User", "Claude-User", "ia-utilisateur", "Claude-User", ""),
    (r"ClaudeBot|anthropic-ai|Claude-Web", "ClaudeBot", "ia-entrainement", "ClaudeBot", ""),
    (r"Perplexity-User", "Perplexity-User", "ia-utilisateur", "Perplexity-User", "ip:perplexity-user"),
    (r"PerplexityBot", "PerplexityBot", "ia-recherche", "PerplexityBot", "ip:perplexity-bot"),
    (r"MistralAI-User", "MistralAI-User", "ia-utilisateur", "MistralAI-User", ""),
    (r"DuckAssistBot", "DuckAssistBot", "ia-utilisateur", "DuckAssistBot", ""),
    (r"YouBot", "YouBot", "ia-recherche", "YouBot", ""),
    (r"meta-externalfetcher", "Meta-ExternalFetcher", "ia-utilisateur", "meta-externalfetcher", ""),
    (r"meta-externalagent", "Meta-ExternalAgent", "ia-entrainement", "meta-externalagent", ""),
    (r"Amazonbot", "Amazonbot", "ia-entrainement", "Amazonbot", ""),
    (r"Bytespider", "Bytespider", "ia-entrainement", "Bytespider", ""),
    (r"CCBot", "CCBot", "ia-entrainement", "CCBot", ""),
    (r"cohere-ai|cohere-training-data-crawler", "Cohere", "ia-entrainement", "cohere-ai", ""),
    (r"Diffbot", "Diffbot", "ia-entrainement", "Diffbot", ""),
    (r"AI2Bot", "AI2Bot", "ia-entrainement", "AI2Bot", ""),
    (r"AhrefsBot|AhrefsSiteAudit", "AhrefsBot", "outil-seo", "AhrefsBot", ""),
    (r"SemrushBot|SiteAuditBot", "SemrushBot", "outil-seo", "SemrushBot", ""),
    (r"MJ12bot", "MJ12bot", "outil-seo", "MJ12bot", ""),
    (r"DotBot", "DotBot", "outil-seo", "DotBot", ""),
    (r"BLEXBot", "BLEXBot", "outil-seo", "BLEXBot", ""),
    (r"DataForSeoBot", "DataForSeoBot", "outil-seo", "DataForSeoBot", ""),
    (r"Screaming Frog", "Screaming Frog", "outil-seo", "Screaming Frog SEO Spider", ""),
    (r"SEOkicks", "SEOkicks", "outil-seo", "SEOkicks", ""),
    (r"Barkrowler", "Barkrowler", "outil-seo", "Barkrowler", ""),
    (r"facebookexternalhit|Facebot", "Facebook (apercu)", "apercu", "facebookexternalhit", ""),
    (r"Twitterbot", "Twitterbot", "apercu", "Twitterbot", ""),
    (r"LinkedInBot", "LinkedInBot", "apercu", "LinkedInBot", ""),
    (r"Slackbot", "Slackbot", "apercu", "Slackbot", ""),
    (r"Discordbot", "Discordbot", "apercu", "Discordbot", ""),
    (r"TelegramBot", "TelegramBot", "apercu", "TelegramBot", ""),
    (r"WhatsApp", "WhatsApp", "apercu", "WhatsApp", ""),
]
IP_LISTS = {
    "google": ["https://developers.google.com/static/search/apis/ipranges/googlebot.json",
               "https://developers.google.com/static/search/apis/ipranges/special-crawlers.json",
               "https://developers.google.com/static/search/apis/ipranges/user-triggered-fetchers.json"],
    "bing": ["https://www.bing.com/toolbox/bingbot.json"],
    "openai-gptbot": ["https://openai.com/gptbot.json"],
    "openai-search": ["https://openai.com/searchbot.json"],
    "openai-user": ["https://openai.com/chatgpt-user.json"],
    "perplexity-bot": ["https://www.perplexity.ai/perplexitybot.json"],
    "perplexity-user": ["https://www.perplexity.ai/perplexity-user.json"],
}
BOT_RE = [(re.compile(p, re.I), n, f, t, v) for p, n, f, t, v in BOTS]
GENERIC_BOT = re.compile(r"bot|crawl|spider|slurp|fetch|scan|curl|wget|python|go-http|java/|libwww|httpclient|headless|axios|node-fetch|okhttp|scrapy|zgrab|masscan", re.I)
FAMILIES = ["moteur", "ia-recherche", "ia-utilisateur", "ia-entrainement", "outil-seo", "apercu", "faux-robot", "autre-robot", "humain-probable"]
FAMILY_LABEL = {
    "moteur": "Moteurs de recherche", "ia-recherche": "IA : index de recherche", "ia-utilisateur": "IA : lecture à la demande d'un utilisateur",
    "ia-entrainement": "IA : entraînement", "outil-seo": "Outils SEO", "apercu": "Aperçus sociaux",
    "faux-robot": "Robots usurpés (faux moteurs, fausses IA)", "autre-robot": "Autres robots et scripts",
    "humain-probable": "Navigateurs (humains probables)",
}
LINE_RE = re.compile(r'^(\S+) \S+ \S+ \[([^\]]+)\] "([A-Z]+) (\S+)[^"]*" (\d{3}) (\S+)(?: "([^"]*)" "([^"]*)")?')
STATIC_RE = re.compile(r"\.(css|js|mjs|map|png|jpe?g|gif|webp|avif|svg|ico|woff2?|ttf|eot|otf|mp4|webm|mp3|pdf|zip|gz)$", re.I)
PROBE_RE = re.compile(r"/\.(env|git|svn|aws|ssh|htpasswd|DS_Store|turbo|changeset|vscode|idea|github)\b|(^|/)wp-(login|config|signup|trackback)\[^/\]*\?\.php|(^|/)wp-admin(/|$)|(^|/)wp-(content|includes)/\.\*\.php|wlwmanifest\.xml|(^|/)xmlrpc\.php|phpmyadmin|(^|/)pma/|adminer|(^|/)vendor/|phpunit|eval-stdin|cgi-bin|(^|/)actuator|(^|/)_profiler|(^|/)telescope|(^|/)config/|(^|/)(lerna|rush|composer|package|tsconfig|config|settings|credentials|secrets)\.json$|\.(sql|bak|old|swp|env|ya?ml|toml|ini|log)$|(^|/)\.well-known/.*\.php|(^|/)api/account|(^|/).(dockerenv|dev.vars)$|(^|/)auth.json$|/v\d+/auth/|(^|/)boaform|(^|/)HNAP1|(^|/)owa/|(^|/)solr/|(^|/)server-status", re.I)
# Fichiers techniques : comptes a part, jamais dans les classements de pages
INFRA_RE = re.compile(r"^/(robots\.txt|ads\.txt|app-ads\.txt|humans\.txt|security\.txt|llms(-full)?\.txt|favicon\.ico|sitemap[^/]*|\.well-known/.*)$", re.I)
TRACKING = re.compile(r"^(utm_\w+|fbclid|gclid|msclkid|yclid|_ga|_gl|mc_cid|mc_eid|ref|ref_src|igshid|sid|phpsessid|sessionid|jsessionid)$", re.I)


def n(x):
    return f"{x:,}".replace(",", " ")


def pct(a, b):
    return f"{100.0 * a / b:.1f} %" if b else "0 %"


def classify(ua):
    for rx, name, family, token, verif in BOT_RE:
        if rx.search(ua):
            return name, family, token, verif
    if not ua or ua == "-" or GENERIC_BOT.search(ua):
        return "Autre robot", "autre-robot", None, ""
    return "Navigateur", "humain-probable", None, ""


def open_log(path):
    if path.endswith(".gz"):
        return io.TextIOWrapper(gzip.open(path, "rb"), encoding="utf-8", errors="replace")
    return open(path, encoding="utf-8", errors="replace")


def url_key(target):
    """Adresse de reference : chemin decode + parametres utiles tries (pistage et session retires)."""
    parts = urllib.parse.urlsplit(target)
    path = urllib.parse.unquote(parts.path or "/")
    path = path if path == "/" else (path.rstrip("/") or "/")
    params = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)]
    tracked = any(TRACKING.match(k) for k, _ in params)
    kept = sorted((k, v) for k, v in params if not TRACKING.match(k))
    key = path + ("?" + urllib.parse.urlencode(kept) if kept else "")
    return key, path, bool(params), tracked


def template(key):
    """Gabarit d'adresse : chiffres remplaces, slug coupe, valeurs de parametres masquees."""
    path, _, query = key.partition("?")
    path = re.sub(r"\d+", "{n}", path)
    path = re.sub(r"(\{n\})[-_][^/]*?(\.[a-z0-9]+)?$", r"\1-...\2", path)
    if query:
        names = sorted({p.split("=")[0] for p in query.split("&")})
        path += "?" + "&".join(f"{k}=*" for k in names)
    return path


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA_TOOL})
    return urllib.request.urlopen(req, timeout=timeout).read()


def load_ip_lists(keys):
    nets, status = {}, {}
    for key in keys:
        nets[key] = []
        for url in IP_LISTS[key]:
            try:
                data = json.loads(fetch(url))
                for p in data.get("prefixes", []):
                    cidr = p.get("ipv4Prefix") or p.get("ipv6Prefix")
                    if cidr:
                        nets[key].append(ipaddress.ip_network(cidr, strict=False))
                status[url] = "ok"
            except Exception as exc:
                status[url] = f"indisponible ({exc.__class__.__name__})"
    return nets, status


def in_nets(ip, nets):
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in nets if net.version == addr.version)


def dns_ok(ip, domains, cache):
    """DNS inverse puis confirmation directe (methode documentee par Google, Bing, Apple, Yandex)."""
    if ip not in cache:
        try:
            host = socket.gethostbyaddr(ip)[0].lower().rstrip(".")
            good = any(host == d or host.endswith("." + d) for d in domains)
            cache[ip] = good and ip in {a[4][0] for a in socket.getaddrinfo(host, None)}
        except Exception:
            cache[ip] = False
    return cache[ip]


def load_sitemap(src, limit=100000):
    seen, todo, keys = set(), [src], set()
    while todo and len(keys) < limit:
        cur = todo.pop()
        if cur in seen:
            continue
        seen.add(cur)
        try:
            data = fetch(cur) if re.match(r"https?://", cur) else open(cur, "rb").read()
            if data[:2] == b"\x1f\x8b":
                data = gzip.decompress(data)
            root = ET.fromstring(data)
        except Exception as exc:
            print(f"sitemap illisible : {cur} ({exc})", file=sys.stderr)
            continue
        is_index = root.tag.endswith("sitemapindex")
        for el in root.iter():
            if el.tag.endswith("loc") and el.text:
                loc = el.text.strip()
                if is_index:
                    todo.append(loc)
                else:
                    sp = urllib.parse.urlsplit(loc)
                    keys.add(url_key(sp.path + ("?" + sp.query if sp.query else ""))[0])
    return keys


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Analyse SEO et GEO de journaux nginx / Apache (format combined).")
    ap.add_argument("logs", nargs="+", help="fichiers de journaux (.log, .gz)")
    ap.add_argument("--days", type=int, default=0, help="ne garder que les N derniers jours (0 = tout)")
    ap.add_argument("--verify", action="store_true", help="démasquer les faux robots (listes d'IP officielles + DNS)")
    ap.add_argument("--dns-limit", type=int, default=100, help="IP vérifiées par DNS pour chaque robot sans liste d'IP (défaut 100)")
    ap.add_argument("--sitemap", help="URL ou fichier du sitemap (adresses jamais vues par Googlebot)")
    ap.add_argument("--robots", help="URL ou fichier robots.txt (robots qui passent outre)")
    ap.add_argument("--top", type=int, default=15, help="taille des classements (défaut 15)")
    ap.add_argument("--out", help="dossier de sortie (rapport.md + adresses.csv) ; sinon rapport sur la sortie standard")
    args = ap.parse_args()

    files = [f for f in args.logs if os.path.isfile(f)]
    if not files:
        sys.exit("Aucun fichier de journal lisible.")
    bad = 0

    def entries():
        """Lecture au fil de l'eau : un journal de plusieurs centaines de Mo ne tient pas en memoire."""
        nonlocal bad
        for path in files:
            with open_log(path) as fh:
                for line in fh:
                    m = LINE_RE.match(line)
                    if not m:
                        bad += 1
                        continue
                    ip, ts, method, target, status, size, _ref, ua = m.groups()
                    try:
                        when = dt.datetime.strptime(ts, "%d/%b/%Y:%H:%M:%S %z")
                    except ValueError:
                        bad += 1
                        continue
                    yield when, ip, method, target, int(status), size, ua or "-"

    # Premier passage (seulement si utile) : date la plus recente et IP par robot verifiable
    limit = None
    verdict = {}          # (robot, ip) -> True authentique / False usurpe / None non verifie
    ip_status = {}
    if args.days or args.verify:
        newest = None
        ips_by_bot = collections.defaultdict(collections.Counter)
        for when, ip, _m, _t, _s, _z, ua in entries():
            newest = when if newest is None or when > newest else newest
            if args.verify:
                name, _f, _t2, verif = classify(ua)
                if verif:
                    ips_by_bot[(name, verif)][ip] += 1
        bad = 0
        if args.days and newest:
            limit = newest - dt.timedelta(days=args.days)
        if args.verify:
            keys = {v[3:] for (_n, v) in ips_by_bot if v.startswith("ip:")}
            nets, ip_status = load_ip_lists(keys)
            cache = {}
            for (name, verif), ips in ips_by_bot.items():
                if verif.startswith("ip:"):
                    lst = nets.get(verif[3:]) or []
                    for ip in ips:
                        verdict[(name, ip)] = in_nets(ip, lst) if lst else None
                else:
                    domains = verif[4:].split(",")
                    for ip, _c in ips.most_common(args.dns_limit):
                        verdict[(name, ip)] = dns_ok(ip, domains, cache)

    # Agregats
    total = 0
    first = last = None
    fam_hits = collections.Counter()
    mk = lambda: {"hits": 0, "family": "", "token": None, "status": collections.Counter(), "urls": collections.Counter(),
                  "static": 0, "params": 0, "tracked": 0, "days": collections.Counter(), "last": None, "unverified": 0}
    bot = collections.defaultdict(mk)
    url_bot = collections.defaultdict(collections.Counter)
    url_status_g = collections.defaultdict(collections.Counter)
    url_last_g = {}
    tpl = collections.defaultdict(collections.Counter)      # famille -> gabarit -> hits
    infra = collections.defaultdict(collections.Counter)    # fichier technique -> famille -> hits
    probes = collections.defaultdict(collections.Counter)   # famille -> chemin sonde -> hits

    for when, ip, method, target, status, size, ua in entries():
        if limit and when < limit:
            continue
        total += 1
        first = when if first is None or when < first else first
        last = when if last is None or when > last else last
        name, family, token, verif = classify(ua)
        v = verdict.get((name, ip)) if verif else True
        if v is False:
            name, family = "Faux " + name, "faux-robot"
        key, path, has_params, tracked = url_key(target)
        if PROBE_RE.search(path):
            probes[family][path] += 1
            fam_hits[family] += 1
            bot[name]["hits"] += 0
            continue
        fam_hits[family] += 1
        is_infra = bool(INFRA_RE.match(path))
        is_static = is_infra or bool(STATIC_RE.search(path))
        if is_infra:
            infra["/sitemap*" if path.lower().startswith("/sitemap") else path.lower()][family] += 1
        b = bot[name]
        b["hits"] += 1
        b["family"], b["token"] = family, token
        b["status"][status] += 1
        b["days"][when.date().isoformat()] += 1
        b["last"] = when if b["last"] is None or when > b["last"] else b["last"]
        if args.verify and ((verif and v is None) or (not verif and family.startswith("ia-"))):
            b["unverified"] += 1
        if has_params:
            b["params"] += 1
        if tracked:
            b["tracked"] += 1
        if is_static:
            b["static"] += 1
            continue
        b["urls"][key] += 1
        if family != "humain-probable":
            url_bot[key][name] += 1
            tpl[family][template(key)] += 1
        if name == "Googlebot":
            url_last_g[key] = max(url_last_g.get(key, when), when)
            url_status_g[key][status] += 1

    # robots.txt
    violations = []
    if args.robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            text = fetch(args.robots).decode("utf-8", "replace") if re.match(r"https?://", args.robots) else open(args.robots, encoding="utf-8", errors="replace").read()
            rp.parse(text.splitlines())
            for name, b in bot.items():
                if b["token"] and b["family"] not in ("apercu", "faux-robot", "ia-utilisateur"):
                    blocked = [(u, c) for u, c in b["urls"].items() if not rp.can_fetch(b["token"], u)]
                    if blocked:
                        violations.append((name, b["family"], sum(c for _, c in blocked), len(blocked), sorted(blocked, key=lambda x: -x[1])[:3]))
        except Exception as exc:
            print(f"robots.txt illisible : {exc}", file=sys.stderr)

    sitemap = load_sitemap(args.sitemap) if args.sitemap else set()

    # --- Rapport ----------------------------------------------------------------------------
    out = []
    w = out.append
    days = max(1, (last - first).days + 1) if first else 1
    code_share = lambda s, lo, hi: sum(c for k, c in s.items() if lo <= k < hi)
    w("# Analyse des journaux : SEO et GEO\n")
    if not first:
        w("Aucune ligne exploitable.")
        print("\n".join(out))
        return
    w(f"- Période : du {first:%d/%m/%Y %H:%M} au {last:%d/%m/%Y %H:%M} ({days} jour{'s' if days > 1 else ''})")
    w(f"- Requêtes analysées : {n(total)}" + (f" ; lignes illisibles : {n(bad)}" if bad else ""))
    w(f"- Fichiers : {len(files)}")
    if args.verify:
        failed = [u for u, s in ip_status.items() if s != "ok"]
        w("- Vérification des robots : listes d'IP officielles et DNS" + (f" ; listes indisponibles : {', '.join(failed)}" if failed else ""))
    else:
        w("- Vérification des robots : non faite (option --verify) ; les chiffres incluent les faux robots")
    w("")

    w("## 1. Qui consomme le serveur\n")
    w("| Famille | Requêtes | Part | Par jour |")
    w("|---|---:|---:|---:|")
    for f in FAMILIES:
        if fam_hits[f]:
            w(f"| {FAMILY_LABEL[f]} | {n(fam_hits[f])} | {pct(fam_hits[f], total)} | {n(fam_hits[f] // days)} |")
    w("")

    w("## 2. Robots identifiés\n")
    w("| Robot | Famille | Requêtes | Pages | Ressources | 3xx | 4xx | 5xx | Pistage | Non vérifié | Dernier passage |")
    w("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
    named = sorted(((k, b) for k, b in bot.items() if b["family"] not in ("humain-probable", "") and b["hits"]), key=lambda x: -x[1]["hits"])
    for name, b in named[: max(args.top * 2, 30)]:
        s, h = b["status"], b["hits"]
        w(f"| {name} | {b['family']} | {n(h)} | {n(h - b['static'])} | {n(b['static'])} | {pct(code_share(s, 300, 400), h)} | {pct(code_share(s, 400, 500), h)} | {pct(code_share(s, 500, 600), h)} | {pct(b['tracked'], h)} | {pct(b['unverified'], h) if b['unverified'] else '-'} | {b['last']:%d/%m %H:%M} |")
    w("\nPages = documents HTML ; Ressources = CSS, JS, images et fichiers techniques ; Pistage = paramètres de suivi ou de session ; Non vérifié = requêtes dont l'IP n'a pas pu être contrôlée (robot sans liste officielle, ou IP au-delà de --dns-limit).")
    w("")

    fakes =[(k, b) for k, b in bot.items() if b["family"] == "faux-robot" and b["hits"]]
    if args.verify:
        w("## 3. Faux robots\n")
        if fakes:
            w("Requêtes dont le user-agent annonce un moteur ou une IA, depuis une IP qui ne lui appartient pas :\n")
            for k, b in sorted(fakes, key=lambda x: -x[1]["hits"]):
                w(f"- {k} : {n(b['hits'])} requêtes, 4xx {pct(code_share(b['status'], 400, 500), b['hits'])}")
            w("\nCes requêtes sont sorties des familles d'origine : les chiffres des sections suivantes ne concernent que les vrais robots.")
        else:
            w("Aucun faux robot parmi les IP vérifiées.")
        w("")

    g = bot.get("Googlebot")
    w("## 4. Budget de crawl de Googlebot\n")
    if g and g["hits"]:
        s, h = g["status"], g["hits"]
        pages = h - g["static"]
        r3, r4, r5 = code_share(s, 300, 400), code_share(s, 400, 500), code_share(s, 500, 600)
        w(f"- {n(h)} requêtes en {days} jour{'s' if days > 1 else ''}, soit {n(h // days)} par jour : {n(pages)} pages et {n(g['static'])} ressources")
        w(f"- {n(len(g['urls']))} adresses de pages distinctes ; {pct(g['params'], h)} des requêtes portent des paramètres")
        w(f"- Gaspillage certain : {pct(r3 + r4 + r5 + g['tracked'], h)} (redirections {pct(r3, h)}, 4xx {pct(r4, h)}, 5xx {pct(r5, h)}, paramètres de pistage ou de session {pct(g['tracked'], h)})")
        freq = collections.Counter(min(c, 10) for c in g["urls"].values())
        w(f"- Fréquence : {n(freq[1])} pages vues une fois, {n(sum(c for k, c in freq.items() if 2 <= k < 10))} de 2 à 9 fois, {n(freq[10])} 10 fois ou plus\n")
        w("Gabarits les plus crawlés par Googlebot :\n")
        gt = collections.Counter(template(u) for u in g["urls"].elements())
        for t, c in gt.most_common(args.top):
            w(f"- {c:>6}  {t[:110]}")
        w("\nPages les plus crawlées :\n")
        for u, c in g["urls"].most_common(args.top):
            w(f"- {c:>6}  {u[:110]}")
        errs = []
        for u, st in url_status_g.items():
            bad_codes = {k: c for k, c in st.items() if k >= 400 or 300 <= k < 400}
            if bad_codes:
                code, c = max(bad_codes.items(), key=lambda x: x[1])
                errs.append((u, sum(bad_codes.values()), code))
        if errs:
            w("\nAdresses en redirection ou en erreur les plus demandées :\n")
            for u, c, code in sorted(errs, key=lambda x: -x[1])[: args.top]:
                w(f"- {c:>6}  {code}  {u[:110]}")
        days_list = sorted(g["days"].items())
        if len(days_list) > 1:
            w("\nPar jour : " + " ; ".join(f"{d[8:]}/{d[5:7]} {c}" for d, c in days_list[-31:]))
    else:
        w("Aucune requête de Googlebot dans la période.")
    w("")

    if sitemap:
        crawled = set(url_last_g)
        seen = sitemap & crawled
        never = sitemap - crawled
        outside = [u for u in crawled if u not in sitemap]
        w("## 5. Sitemap et crawl de Googlebot\n")
        w(f"- Adresses du sitemap : {n(len(sitemap))} ; vues par Googlebot dans la période : {n(len(seen))} ({pct(len(seen), len(sitemap))})")
        nt = collections.Counter(template(u) for u in never)
        w(f"- Jamais vues : {n(len(never))}. Par gabarit : " + ", ".join(f"{t} ({c})" for t, c in nt.most_common(6)))
        ot = collections.Counter()
        for u in outside:
            ot[template(u)] += sum(url_bot[u].values())
        w(f"- Crawlées hors sitemap : {n(len(outside))} adresses. Gabarits les plus demandés : " + ", ".join(f"{t} ({c})" for t, c in ot.most_common(6)))
        w("")

    w("## 6. GEO : ce que lisent les IA\n")
    for fam in ("ia-utilisateur", "ia-recherche", "ia-entrainement"):
        group = [(k, b) for k, b in bot.items() if b["family"] == fam and b["hits"]]
        hits = sum(b["hits"] for _, b in group)
        w(f"### {FAMILY_LABEL[fam]} : {n(hits)} requêtes\n")
        if not hits:
            w("Aucune.\n")
            continue
        for k, b in sorted(group, key=lambda x: -x[1]["hits"]):
            r4 = code_share(b["status"], 400, 500) / max(1, b["hits"])
            extra = (", IP non vérifiable" if b["unverified"] else "") + (" ; taux de 4xx anormal, probablement usurpé en partie" if r4 > 0.3 else "")
            w(f"- {k} : {n(b['hits'])} requêtes, {n(len(b['urls']))} pages, 4xx {pct(code_share(b['status'], 400, 500), b['hits'])}{extra}")
        top = collections.Counter()
        for _k, b in group:
            top.update(b["urls"])
        w("\nPages les plus lues :\n")
        for u, c in top.most_common(args.top):
            w(f"- {c:>6}  {u[:110]}")
        w("\nGabarits les plus lus : " + ", ".join(f"{t} ({c})" for t, c in tpl[fam].most_common(8)))
        w("")

    if violations:
        w("## 7. robots.txt : interdits mais demandés\n")
        for name, fam, hits, cnt, ex in sorted(violations, key=lambda x: -x[2]):
            w(f"- {name} ({fam}) : {n(hits)} requêtes sur {n(cnt)} adresses interdites, par exemple " + ", ".join(u[:60] for u, _ in ex))
        w("")

    if infra:
        w("## 8. Fichiers techniques\n")
        for f_name, by_fam in sorted(infra.items(), key=lambda x: -sum(x[1].values()))[:12]:
            w(f"- {f_name} : {n(sum(by_fam.values()))} requêtes (" + ", ".join(f"{FAMILY_LABEL[k]} {c}" for k, c in by_fam.most_common(4)) + ")")
        if not any(k.startswith("/llms") for k in infra):
            w("- /llms.txt : aucune requête dans la période")
        w("")

    if probes:
        w("## 9. Sondes de sécurité (chemins d'attaque connus)\n")
        for fam in FAMILIES:
            if probes[fam]:
                w(f"- {FAMILY_LABEL[fam]} : {n(sum(probes[fam].values()))} requêtes, par exemple " + ", ".join(p[:40] for p, _ in probes[fam].most_common(4)))
        w("\nCes requêtes sont exclues des classements de pages ci-dessus.")
        w("")

    report = "\n".join(out)
    if args.out:
        os.makedirs(args.out, exist_ok=True)
        with open(os.path.join(args.out, "rapport.md"), "w", encoding="utf-8") as fh:
            fh.write(report)
        cols = [k for k, b in named if b["family"] != "faux-robot"][:20]
        with open(os.path.join(args.out, "adresses.csv"), "w", encoding="utf-8", newline="") as fh:
            wr = csv.writer(fh, delimiter=";")
            wr.writerow(["adresse", "gabarit", "total robots", "dernier Googlebot", "dans le sitemap"] + cols)
            for u, c in sorted(url_bot.items(), key=lambda x: -sum(x[1].values())):
                lg = url_last_g.get(u)
                wr.writerow([u, template(u), sum(c.values()), lg.strftime("%Y-%m-%d") if lg else "", ("oui" if u in sitemap else "non") if sitemap else ""] + [c.get(k, 0) for k in cols])
        print(f"Rapport : {os.path.join(args.out, 'rapport.md')}\nAdresses : {os.path.join(args.out, 'adresses.csv')}")
    else:
        print(report)


if __name__ == "__main__":
    main()
