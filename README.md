# Retro Rewind France

Le site de la communauté française de Retro Rewind (Mario Kart Wii) : **https://retrorewindfr.com**

## Modifier le site

Tout se fait dans le dossier **`donnees`**, directement sur GitHub :
ouvre le fichier, clique sur le crayon ✏️ (« Edit this file »), fais ta modif, puis clique sur **Commit changes**.
Le site se met à jour tout seul en 1 à 2 minutes.

| Fichier | À quoi il sert |
|---|---|
| `donnees/joueurs.txt` | Le classement FR : un code ami par ligne (note facultative après `\|`) |
| `donnees/tds.txt` | Le classement TDS : `pseudo \| points \| code ami` |
| `donnees/roles.txt` | Les rôles TDS : `nom \| points minimum` |
| `donnees/tournois.txt` | Tournois spéciaux et résultats : `date \| heure \| nom \| format \| 1er, 2e, 3e` |
| `donnees/reglages.txt` | Lien Discord, créneaux des tournois, textes du site |

Les VR, le top FR, le top monde, les Mii, les stats de course des joueurs, la liste des circuits,
la méta en ligne et le top mondial se mettent à jour **tout seuls toutes les heures** (données Retro WFC).
Le bloc « En direct » de l'accueil se met à jour chaque minute directement depuis rwfc.net.

⚠️ Ne modifie pas `donnees/stats.json`, `donnees/rwfc.json` ni le dossier `donnees/mii` : ils sont remplis automatiquement.

## Si quelque chose ne marche pas

Onglet **Actions** du dépôt : chaque mise à jour y apparaît. Une croix rouge = une erreur, clique dessus pour voir le message.
Une ligne mal écrite dans un fichier `.txt` est simplement ignorée (avec un avertissement jaune), le site reste en ligne.

## Fonctionnement (pour info)

- `outils/sync.py` va chercher les données sur Retro WFC (rwfc.net) → `donnees/stats.json`, `donnees/rwfc.json` et `donnees/mii/`.
- `outils/build.py` fabrique le site à partir de `site/modele.html` et des données → dossier `_site`.
- `.github/workflows/site.yml` lance les deux toutes les heures et à chaque modification, puis publie sur GitHub Pages.

Site de fans, sans lien avec Nintendo ni avec l'équipe Retro Rewind.
