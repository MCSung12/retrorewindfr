#!/usr/bin/env python3
"""Va chercher les données Retro WFC (rwfc.net) pour le site.

- donnees/stats.json : VR, rangs, stats de course et évolution du VR de chaque joueur de joueurs.txt
- donnees/mii/<code>.png : les Mii
- donnees/rwfc.json : liste des circuits, stats globales, top mondial

Si Retro WFC ne répond pas, les anciennes données sont gardées.
Lancé automatiquement toutes les heures par GitHub (voir .github/workflows/site.yml).
"""
import base64
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DONNEES = os.path.join(RACINE, 'donnees')
API = 'https://rwfc.net/api/'
UA = 'RetroRewindFrance-site/1.1 (+https://retrorewindfr.com; synchro horaire)'
PUA = re.compile('[' + chr(0xE000) + '-' + chr(0xF8FF) + ']')
MAINTENANT = datetime.datetime.now(datetime.timezone.utc)
ISO = MAINTENANT.strftime('%Y-%m-%dT%H:%M:%SZ')


class Introuvable(Exception):
    pass


def api(chemin):
    req = urllib.request.Request(API + chemin, headers={'User-Agent': UA, 'Accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise Introuvable()
        raise
    finally:
        time.sleep(0.35)


def codes_joueurs():
    codes = []
    with open(os.path.join(DONNEES, 'joueurs.txt'), encoding='utf-8-sig') as f:
        for ligne in f:
            ligne = ligne.strip()
            if not ligne or ligne.startswith('#'):
                continue
            chiffres = re.sub(r'\D', '', ligne.split('|')[0])
            if len(chiffres) == 12 and chiffres not in codes:
                codes.append(chiffres)
    return codes


def fc(chiffres):
    return '-'.join(chiffres[i:i + 4] for i in (0, 4, 8))


def entier(v, defaut=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return defaut


def nom(v):
    return PUA.sub('', str(v or '')).strip()[:40]


def lire_json(chemin, defaut):
    try:
        with open(chemin, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return defaut


def ecrire_json(chemin, obj, **kw):
    with open(chemin, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, **kw)
        f.write('\n')


def age_heures(iso):
    try:
        t = datetime.datetime.strptime(iso, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=datetime.timezone.utc)
        return (MAINTENANT - t).total_seconds() / 3600
    except (TypeError, ValueError):
        return 1e9


def stats_course(pid):
    s = api('racestats/player/' + str(pid))
    top = (s.get('topCombosByWinCount') or s.get('topCombos') or [])
    combo = None
    if top:
        c = top[0]
        combo = [c.get('name'), entier(c.get('raceCount'), 0), c.get('winRate')]
    return {
        'races': entier(s.get('totalRaces'), 0),
        'combo': combo,
        'chars': [[c.get('name'), entier(c.get('raceCount'), 0)] for c in (s.get('topCharacters') or [])[:3]],
        'vehs': [[c.get('name'), entier(c.get('raceCount'), 0)] for c in (s.get('topVehicles') or [])[:3]],
        'tracks': [[c.get('trackName'), entier(c.get('raceCount'), 0)] for c in (s.get('topTracks') or [])[:3]],
        'recent': [[str(c.get('timestamp') or '')[:16], c.get('trackName'), entier(c.get('finishPos')), entier(c.get('playerCount'))]
                   for c in (s.get('recentRaces') or [])[:5]],
    }


def historique(code):
    h = api('leaderboard/player/' + fc(code) + '/history')
    depuis = (MAINTENANT - datetime.timedelta(days=45)).strftime('%Y-%m-%d')
    par_jour = {}
    for e in h.get('history') or []:
        jour = str(e.get('date') or '')[:10]
        vr = entier(e.get('totalVR'))
        if jour >= depuis and vr is not None:
            par_jour[jour] = vr
    return [[j, par_jour[j]] for j in sorted(par_jour)]


def synchro_joueurs():
    chemin = os.path.join(DONNEES, 'stats.json')
    stats = lire_json(chemin, {})
    joueurs = stats.get('joueurs') if isinstance(stats.get('joueurs'), dict) else {}
    os.makedirs(os.path.join(DONNEES, 'mii'), exist_ok=True)
    ok = introuvables = erreurs = mii = 0
    codes = codes_joueurs()
    for code in codes:
        ancien = joueurs.get(code) if isinstance(joueurs.get(code), dict) else {}
        x = dict(ancien.get('x') or {})
        try:
            r = api('leaderboard/player/' + fc(code))
        except Introuvable:
            r = None
        except Exception as e:
            print(f'  {fc(code)} : pas de réponse ({e.__class__.__name__}), anciennes stats gardées')
            erreurs += 1
            continue
        if r is None or re.sub(r'\D', '', str(r.get('friendCode') or '')) != code:
            print(f'  {fc(code)} : introuvable sur Retro WFC')
            if not isinstance(ancien.get('vr'), int):
                joueurs[code] = {'error': 'notfound'}
            introuvables += 1
            continue
        vr = entier(r.get('vr'))
        if vr is None:
            erreurs += 1
            continue
        vs = r.get('vrStats') if isinstance(r.get('vrStats'), dict) else {}
        x.update({'pid': str(r.get('pid') or ''), 'veh': r.get('vehiclePreference'),
                  'vrank': entier(r.get('vehicleRank')), 'd24': entier(vs.get('last24Hours'), 0)})
        if x.get('pid'):
            try:
                x.update(stats_course(x['pid']))
            except Exception as e:
                print(f'  {fc(code)} : stats de course indisponibles ({e.__class__.__name__})')
        if age_heures(x.get('histAt')) > 20:
            try:
                x['hist'] = historique(code)
                x['histAt'] = ISO
            except Exception as e:
                print(f'  {fc(code)} : historique indisponible ({e.__class__.__name__})')
        x['at'] = ISO
        joueurs[code] = {
            'name': nom(r.get('name'))[:24],
            'vr': vr,
            'rank': entier(r.get('rank')),
            'lastSeen': r.get('lastSeen'),
            'week': entier(vs.get('lastWeek'), 0),
            'month': entier(vs.get('lastMonth'), 0),
            'sus': bool(r.get('isSuspicious')),
            'x': x,
        }
        ok += 1
        b64 = r.get('miiImageBase64')
        if isinstance(b64, str) and b64:
            try:
                octets = base64.b64decode(b64, validate=True)
            except ValueError:
                octets = b''
            if octets[:8] == b'\x89PNG\r\n\x1a\n':
                fichier = os.path.join(DONNEES, 'mii', code + '.png')
                if not os.path.exists(fichier) or open(fichier, 'rb').read() != octets:
                    with open(fichier, 'wb') as f:
                        f.write(octets)
                    mii += 1
    for code in list(joueurs):
        if code not in codes:
            del joueurs[code]
    stats['joueurs'] = joueurs
    if ok:
        stats['statsAt'] = ISO
    ecrire_json(chemin, stats, indent=1, sort_keys=True)
    print(f'Joueurs : {ok} à jour, {introuvables} introuvable(s), {erreurs} sans réponse, {mii} Mii mis à jour.')
    return ok, erreurs, len(codes)


def synchro_globale():
    chemin = os.path.join(DONNEES, 'rwfc.json')
    rw = lire_json(chemin, {})
    fait = []
    try:
        pistes = [t for t in api('timetrial/tracks') if not t.get('isHidden')]
        pistes.sort(key=lambda t: (entier(t.get('sortOrder'), 0), entier(t.get('id'), 0)))
        groupes = {}
        for t in pistes:
            cid = entier(t.get('courseId'))
            if cid is None:
                continue
            if cid not in groupes:
                groupes[cid] = [cid, 'R' if t.get('category') == 'retro' else 'C', entier(t.get('laps'), 3), []]
            if t.get('name') and t['name'] not in groupes[cid][3]:
                groupes[cid][3].append(t['name'])
        if groupes:
            rw['tracks'] = list(groupes.values())
            fait.append('circuits')
    except Exception as e:
        print(f'  circuits indisponibles ({e.__class__.__name__})')
    try:
        g = api('racestats/global')
        rw['counts'] = {str(t.get('courseId')): entier(t.get('raceCount'), 0) for t in g.get('allPlayedTracks') or []}
        rw['global'] = {
            'races': entier(g.get('totalRacesTracked'), 0),
            'players': entier(g.get('uniquePlayersCount'), 0),
            'since': g.get('trackedSince'),
            'chars': [[c.get('name'), entier(c.get('raceCount'), 0)] for c in (g.get('topCharacters') or [])[:8]],
            'vehs': [[c.get('name'), entier(c.get('raceCount'), 0)] for c in (g.get('topVehicles') or [])[:8]],
            'combos': [[c.get('name'), entier(c.get('raceCount'), 0), c.get('winRate')] for c in (g.get('topCombosByWinCount') or [])[:8]],
            'hours': [entier(c.get('raceCount'), 0) for c in sorted(g.get('racesByHour') or [], key=lambda c: entier(c.get('hour'), 0))],
            'days': [[c.get('dayName'), entier(c.get('raceCount'), 0)] for c in (g.get('racesByDayOfWeek') or [])],
        }
        fait.append('stats globales')
    except Exception as e:
        print(f'  stats globales indisponibles ({e.__class__.__name__})')
    try:
        lb = api('leaderboard?page=1&pageSize=10')
        rw['world'] = {
            'top': [[entier(p.get('rank')), nom(p.get('name')), entier(p.get('vr')), p.get('vehiclePreference'),
                     re.sub(r'\D', '', str(p.get('friendCode') or ''))] for p in lb.get('players') or []],
            'total': entier((lb.get('stats') or {}).get('totalPlayers') or lb.get('totalCount'), 0),
            'at': ISO,
        }
        fait.append('top mondial')
    except Exception as e:
        print(f'  top mondial indisponible ({e.__class__.__name__})')
    if fait:
        rw['at'] = ISO
        ecrire_json(chemin, rw, separators=(',', ':'))
    print('Global : ' + (', '.join(fait) if fait else 'rien de mis à jour') + '.')


def main():
    ok, erreurs, total = synchro_joueurs()
    synchro_globale()
    if total and not ok and erreurs:
        print("::warning::Retro WFC n'a répondu pour aucun joueur : le site garde les dernières stats connues.")


if __name__ == '__main__':
    main()
    sys.exit(0)
