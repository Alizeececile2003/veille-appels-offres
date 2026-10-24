import json, datetime, urllib.request, urllib.parse

# Mots qui signalent un appel d'offres dans le métier
MOTS_CLES = ["tribune", "gradin", "scène", "scene", "podium", "chapiteau",
             "échafaudage", "echafaudage", "barrière", "barriere", "tente",
             "estrade", "festival", "spectacle", "événementiel", "evenementiel",
             "location de matériel", "praticable", "structure temporaire"]

def texte(v):
    if isinstance(v, list):
        return " ".join(str(x) for x in v)
    return str(v or "")

# 1. Récupérer les avis BOAMP des 2 derniers jours
depuis = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
params = urllib.parse.urlencode({"where": f"dateparution >= date'{depuis}'", "limit": -1})
url = "https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/exports/json?" + params
with urllib.request.urlopen(url, timeout=180) as r:
    avis = json.load(r)

# 2. Reprendre la liste déjà récoltée
try:
    with open("data.json", encoding="utf-8") as f:
        liste = {a["id"]: a for a in json.load(f)}
except Exception:
    liste = {}

# 3. Trier
for a in avis:
    objet = texte(a.get("objet")).lower()
    desc = texte(a.get("descripteur_libelle")).lower()
    trouves = [m for m in MOTS_CLES if m in objet]
    if trouves:
        statut = "pertinent"
    elif any(m in desc for m in MOTS_CLES):
        statut = "à vérifier"
    else:
        continue
    liste[a.get("idweb")] = {
        "id": a.get("idweb"),
        "objet": texte(a.get("objet")),
        "acheteur": texte(a.get("nomacheteur")),
        "departement": texte(a.get("code_departement")),
        "parution": texte(a.get("dateparution")),
        "date_limite": texte(a.get("datelimitereponse")),
        "lien": texte(a.get("url_avis")),
        "mots": trouves,
        "statut": statut,
    }

# 4. Retirer les avis dont la date limite est passée
aujourdhui = datetime.date.today().isoformat()
garder = [a for a in liste.values() if not a["date_limite"] or a["date_limite"][:10] >= aujourdhui]
garder.sort(key=lambda a: a["date_limite"] or "9999")

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(garder, f, ensure_ascii=False, indent=1)
print(len(garder), "appels d'offres gardés")
