import json, re, datetime, unicodedata, urllib.request, urllib.parse

def simple(t):
    t = str(t or "").lower().replace("’", "'")
    t = unicodedata.normalize("NFD", t)
    return "".join(c for c in t if unicodedata.category(c) != "Mn")

# Mots qui signalent un appel d'offres dans le métier (sans accents)
MOTS_CLES = ["tribune mobile", "gradin", "podium", "chapiteau", "echafaudage",
             "crash barriere", "tente", "estrade", "praticable",
             "regie generale", "regie technique", "tour de regie", "totem",
             "pont lumiere", "structure alu", "structure metallo-textile",
             "structure textile", "pagode", "couverture de scene", "barnum",
             "stand", "festivites", "concert", "foire", "ceremonie",
             "festival", "evenementiel", "evenementielle", "structure temporaire"]

# Expressions qui disqualifient une annonce
EXCLUSIONS = ["salle des fetes", "manifestation d'interet", "stand de tir", "materiel electrique", "accueil physique", "maitrise d'oeuvre", "maitrise d'œuvre", "conception graphique", "communication visuelle"]

def motif(m):
    return r"\b" + r"s?\s+".join(re.escape(x) for x in m.split()) + r"s?\b"

def trouve(t, mots):
    t = simple(t)
    return [m for m in mots if re.search(motif(m), t)]

def texte(v):
    if isinstance(v, list):
        return " ".join(str(x) for x in v)
    return str(v or "")

# 1. Récupérer les avis BOAMP des 7 derniers jours
depuis = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
params = urllib.parse.urlencode({"where": f"dateparution >= date'{depuis}'", "limit": -1})
url = "https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/exports/json?" + params
with urllib.request.urlopen(url, timeout=180) as r:
    avis = json.load(r)

# 2. Reprendre la liste déjà récoltée (sans les annonces qui ne correspondent plus)
try:
    with open("data.json", encoding="utf-8") as f:
        liste = {a["id"]: a for a in json.load(f)
                 if trouve(a["objet"], MOTS_CLES) and not trouve(a["objet"], EXCLUSIONS)}
except Exception:
    liste = {}

# 3. Trier
for a in avis:
    objet = texte(a.get("objet"))
    desc = texte(a.get("descripteur_libelle"))
    if trouve(objet, EXCLUSIONS):
        continue
    trouves = trouve(objet, MOTS_CLES)
    if trouves:
        statut = "pertinent"
    elif trouve(desc, MOTS_CLES):
        statut = "à vérifier"
    else:
        continue
    liste[a.get("idweb")] = {
        "id": a.get("idweb"),
        "objet": objet,
        "acheteur": texte(a.get("nomacheteur")),
        "departement": texte(a.get("code_departement")),
        "parution": texte(a.get("dateparution")),
        "date_limite": texte(a.get("datelimitereponse")),
        "lien": texte(a.get("url_avis")),
        "mots": trouves,
        "statut": statut,
        "procedure": texte(a.get("procedure_libelle")),
        "famille": texte(a.get("famille_libelle")),
    }

# 4. Retirer les avis dont la date limite est passée
aujourdhui = datetime.date.today().isoformat()
garder = [a for a in liste.values() if not a["date_limite"] or a["date_limite"][:10] >= aujourdhui]
garder.sort(key=lambda a: a["date_limite"] or "9999")

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(garder, f, ensure_ascii=False, indent=1)
print(len(garder), "appels d'offres gardés")
