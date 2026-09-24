#!/usr/bin/env python3
"""Construit le site dans le dossier _site à partir de site/modele.html et des fichiers de donnees/.

Une ligne mal écrite dans un fichier .txt est ignorée (avec un avertissement)
au lieu de faire planter le site.
"""
import datetime
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DONNEES = os.path.join(RACINE, 'donnees')
SITE = os.path.join(RACINE, 'site')
SORTIE = os.path.join(RACINE, '_site')
JOURS = {'dimanche': 0, 'lundi': 1, 'mardi': 2, 'mercredi': 3, 'jeudi': 4, 'vendredi': 5, 'samedi': 6}
BAD = {'<', '>', '%', '&', chr(0x2028), chr(0x2029)}
avertissements = []


def avertir(msg):
    avertissements.append(msg)
    print('::warning::' + msg)


def lignes(nom):
    chemin = os.path.join(DONNEES, nom)
    if not os.path.exists(chemin):
        return []
    out = []
    with open(chemin, encoding='utf-8-sig') as f:
        for n, ligne in enumerate(f, 1):
            ligne = ligne.strip()
            if ligne and not ligne.startswith('#'):
                out.append((n, ligne))
    return out


def chiffres(texte):
    return re.sub(r'\D', '', texte or '')


def format_code(c):
    return '-'.join(c[i:i + 4] for i in (0, 4, 8))


def date_git(*noms):
    """Date du dernier commit qui a touché ces fichiers (sinon maintenant)."""
    try:
        out = subprocess.run(['git', 'log', '-1', '--format=%cI', '--'] + [os.path.join('donnees', n) for n in noms],
                             cwd=RACINE, capture_output=True, text=True, timeout=20).stdout.strip()
        if out:
            return datetime.datetime.fromisoformat(out).astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    except Exception:
        pass
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def safe(o):
    s = json.dumps(o, ensure_ascii=False, separators=(',', ':'))
    return ''.join('\\u%04x' % ord(c) if c in BAD else c for c in s)


def lire_reglages():
    r = {'avantage_discord': []}
    for n, ligne in lignes('reglages.txt'):
        if ':' not in ligne:
            avertir(f'reglages.txt ligne {n} ignorée (il manque « : »)')
            continue
        cle, val = ligne.split(':', 1)
        cle, val = cle.strip().lower(), val.strip()
        if cle == 'avantage_discord':
            if val:
                r['avantage_discord'].append(val)
        else:
            r[cle] = val
    return r


def main():
    reg = lire_reglages()
    adresse = (reg.get('adresse_du_site') or 'https://retrorewindfr.com').rstrip('/')
    try:
        with open(os.path.join(DONNEES, 'stats.json'), encoding='utf-8') as f:
            stats = json.load(f)
    except (OSError, ValueError):
        stats = {}
    st_joueurs = stats.get('joueurs') if isinstance(stats.get('joueurs'), dict) else {}

    if os.path.isdir(SORTIE):
        shutil.rmtree(SORTIE)
    os.makedirs(os.path.join(SORTIE, 'mii'))
    os.makedirs(os.path.join(SORTIE, 'assets'))

    # ---- joueurs
    joueurs, vus = [], set()
    for n, ligne in lignes('joueurs.txt'):
        partie = ligne.split('|', 1)
        c = chiffres(partie[0])
        if len(c) != 12:
            avertir(f'joueurs.txt ligne {n} ignorée : « {partie[0].strip()} » n\'est pas un code ami à 12 chiffres')
            continue
        if c in vus:
            continue
        vus.add(c)
        p = {'id': 'p' + c, 'code': format_code(c), 'note': partie[1].strip()[:40] if len(partie) > 1 else ''}
        s = st_joueurs.get(c)
        p['stats'] = dict(s, at=stats.get('statsAt')) if isinstance(s, dict) else None
        p['mii'] = None
        for ext in ('png', 'webp'):
            src = os.path.join(DONNEES, 'mii', f'{c}.{ext}')
            if os.path.exists(src):
                octets = open(src, 'rb').read()
                shutil.copyfile(src, os.path.join(SORTIE, 'mii', f'{c}.{ext}'))
                p['mii'] = f'mii/{c}.{ext}?v={hashlib.md5(octets).hexdigest()[:8]}'
                break
        joueurs.append(p)

    # ---- rôles et TDS
    roles = []
    for n, ligne in lignes('roles.txt'):
        partie = [x.strip() for x in ligne.split('|')]
        if len(partie) < 2 or not partie[0] or not chiffres(partie[1]):
            avertir(f'roles.txt ligne {n} ignorée (format : nom | points)')
            continue
        roles.append({'name': partie[0][:30], 'min': int(chiffres(partie[1]))})
    tds = []
    for n, ligne in lignes('tds.txt'):
        partie = [x.strip() for x in ligne.split('|')]
        if len(partie) < 2 or not partie[0] or not re.fullmatch(r'\d+', partie[1].replace(' ', '')):
            avertir(f'tds.txt ligne {n} ignorée (format : pseudo | points | code ami)')
            continue
        pid = None
        if len(partie) > 2 and partie[2]:
            c = chiffres(partie[2])
            if c in vus:
                pid = 'p' + c
            else:
                avertir(f'tds.txt ligne {n} : le code {partie[2]} n\'est pas dans joueurs.txt, pas de Mii pour {partie[0]}')
        tds.append({'id': f't{n}', 'name': partie[0][:30], 'playerId': pid, 'points': int(partie[1].replace(' ', ''))})

    # ---- réglages
    slots = []
    for bout in (reg.get('creneaux') or '').split(','):
        m = re.fullmatch(r'\s*([a-zA-Zéèû]+)\s+(\d{1,2})[:h](\d{2})\s*', bout)
        if m and m.group(1).lower() in JOURS:
            slots.append({'day': JOURS[m.group(1).lower()], 'time': f'{int(m.group(2)):02d}:{m.group(3)}'})
        elif bout.strip():
            avertir(f'créneau ignoré : « {bout.strip()} » (format : samedi 21:30)')
    settings = {
        'tagline': reg.get('accroche', ''),
        'discordUrl': reg.get('lien_discord', ''),
        'discordText': reg.get('texte_discord', ''),
        'discordPerks': reg['avantage_discord'],
        'tournamentInfo': reg.get('infos_tournoi', ''),
        'nightlyEnabled': bool(slots),
        'slots': slots,
        'nightlyTitle': reg.get('titre_tournoi') or 'Tournoi du soir',
        'nightlyFormat': reg.get('format_tournoi', ''),
    }

    # ---- tournois spéciaux et résultats
    tournois = []
    for n, ligne in lignes('tournois.txt'):
        partie = [x.strip() for x in ligne.split('|')]
        if len(partie) < 3:
            avertir(f'tournois.txt ligne {n} ignorée (format : date | heure | nom | format | 1er, 2e, 3e)')
            continue
        d = partie[0]
        m = re.fullmatch(r'(\d{1,2})/(\d{1,2})/(\d{4})', d)
        if m:
            d = f'{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}'
        hm = re.fullmatch(r'(\d{1,2})[:h](\d{2})', partie[1])
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', d) or not hm or not partie[2]:
            avertir(f'tournois.txt ligne {n} ignorée (date au format 2026-10-04 ou 04/10/2026, heure au format 21:30)')
            continue
        t = {'id': f'tr{n}', 'date': d, 'time': f'{int(hm.group(1)):02d}:{hm.group(2)}', 'title': partie[2][:60], 'duration': 120}
        if len(partie) > 3 and partie[3]:
            t['details'] = partie[3][:60]
        if len(partie) > 4 and partie[4]:
            t['podium'] = [x.strip()[:24] for x in partie[4].split(',')][:3]
        tournois.append(t)

    # ---- données Retro WFC (circuits, stats globales, top mondial)
    try:
        with open(os.path.join(DONNEES, 'rwfc.json'), encoding='utf-8') as f:
            rwfc = json.load(f)
    except (OSError, ValueError):
        rwfc = None

    data = {
        'version': 3,
        'settings': settings,
        'players': joueurs,
        'tournaments': tournois,
        'rwfc': rwfc,
        'assets': {'heroBg': 'assets/earth.webp'},
        'tds': {'tiers': roles, 'rows': tds, 'at': date_git('tds.txt', 'roles.txt')},
        'statsAt': stats.get('statsAt'),
        'updatedAt': date_git('joueurs.txt', 'tds.txt', 'roles.txt', 'reglages.txt'),
    }

    # ---- page
    modele = open(os.path.join(SITE, 'modele.html'), encoding='utf-8').read()
    for m in ('%%DATA%%', '%%TPL%%', '<!--rrf:body-->'):
        if modele.count(m) != 1:
            sys.exit('modele.html invalide : ' + m)
    page = modele.replace('%%DATA%%', safe(data)).replace('%%TPL%%', 'null')
    tete, corps = page.split('<!--rrf:body-->')
    tete = re.sub(r'<title>.*?</title>\s*', '', tete, count=1)
    titre = 'Retro Rewind France · Classement FR, tournois et tuto Mario Kart Wii'
    desc = ('Retro Rewind France, la communauté française de Retro Rewind sur Mario Kart Wii : '
            'classement des meilleurs joueurs FR, tournois du week-end, tuto pour installer WiiCompiled et Discord.')
    e = html.escape
    jsonld = safe({'@context': 'https://schema.org', '@type': 'WebSite', 'name': 'Retro Rewind France',
                   'alternateName': ['RRF', 'Retro Rewind FR'], 'url': adresse + '/', 'inLanguage': 'fr-FR',
                   'description': desc})
    seo = f'''<title>{e(titre)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(adresse)}/">
<meta name="robots" content="index, follow">
<meta name="theme-color" content="#040816">
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<link rel="icon" href="favicon-32.png" sizes="32x32" type="image/png">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<meta property="og:type" content="website">
<meta property="og:locale" content="fr_FR">
<meta property="og:site_name" content="Retro Rewind France">
<meta property="og:title" content="Retro Rewind France">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(adresse)}/">
<meta property="og:image" content="{e(adresse)}/og-image.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Retro Rewind France">
<meta name="twitter:description" content="{e(desc)}">
<meta name="twitter:image" content="{e(adresse)}/og-image.jpg">
<script type="application/ld+json">{jsonld}</script>
'''
    doc = ('<!doctype html>\n<html lang="fr">\n<head>\n<meta charset="utf-8">\n'
           '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
           + seo + tete + '\n</head>\n<body>\n' + corps + '\n</body>\n</html>\n')
    open(os.path.join(SORTIE, 'index.html'), 'w', encoding='utf-8').write(doc)

    # ---- fichiers fixes
    shutil.copyfile(os.path.join(SITE, 'earth.webp'), os.path.join(SORTIE, 'assets', 'earth.webp'))
    for nom in ('og-image.jpg', 'favicon.svg', 'favicon-32.png', 'apple-touch-icon.png', '404.html'):
        src = os.path.join(SITE, nom)
        if os.path.exists(src):
            shutil.copyfile(src, os.path.join(SORTIE, nom))
    jour = datetime.date.today().isoformat()
    open(os.path.join(SORTIE, 'robots.txt'), 'w').write(f'User-agent: *\nAllow: /\n\nSitemap: {adresse}/sitemap.xml\n')
    open(os.path.join(SORTIE, 'sitemap.xml'), 'w').write(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f'  <url><loc>{adresse}/</loc><lastmod>{jour}</lastmod><changefreq>daily</changefreq><priority>1.0</priority></url>\n'
        '</urlset>\n')

    print(f'Site construit : {len(joueurs)} joueurs, {len(tds)} lignes TDS, {len(roles)} rôles, '
          f'{sum(1 for p in joueurs if p["mii"])} Mii, {len(tournois)} tournoi(s), '
          f'{len((rwfc or {}).get("tracks") or [])} circuits, {len(avertissements)} avertissement(s).')


if __name__ == '__main__':
    main()
