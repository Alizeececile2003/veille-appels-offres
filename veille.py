import json, re, datetime, unicodedata, urllib.request, urllib.parse

# Montant minimum en euros HT. Mettre 150000 si la veille est trop vide.
SEUIL = 200000

def simple(t):
    t = str(t or "").lower().replace("’", "'")
    t = unicodedata.normalize("NFD", t)
    return "".join(c for c in t if unicodedata.category(c) != "Mn")

# Mots de STRUCTURE (sans accents) - "tente" retiré à la demande de Ben
STRUCTURE = ["structure ephemere", "structure temporaire", "structure alu",
             "structure metallo-textile", "structure textile", "structure scenique",
             "echafaudage", "tribune", "gradin", "scene", "podium", "estrade",
             "praticable", "chapiteau", "pagode", "barnum",
             "couverture de scene", "tour de regie", "pont lumiere",
             "crash barriere", "totem", "regie generale", "regie technique"]

# Mots d'ÉVÉNEMENT (sans accents)
EVENEMENT = ["festival", "concert", "tournee", "production", "spectacle",
             "stade", "evenement", "evenementiel", "evenementielle",
             "festivites", "foire", "salon", "ceremonie", "manifestation",
             "fete", "show", "competition", "championnat", "olympique"]

# Filet de sécurité : expressions qui disqualifient une annonce
EXCLUSIONS = ["tente", "salle des fetes", "manifestation d'interet", "stand de tir", "materiel electrique", "accueil physique", "maitrise d'oeuvre", "conception graphique", "communication visuelle", "nettoyage", "entretien des locaux", "traiteur", "restauration collective", "repas", "denrees alimentaires", "cantine", "billetterie", "imprimerie", "impression", "reprographie", "affranchissement", "courrier", "publication", "annonces legales", "traduction", "assurance", "mutuelle", "prevoyance", "recrutement", "interim", "formation", "audit", "etude", "diagnostic", "geometre", "topographique", "controle technique", "informatique", "logiciel", "telephonie", "videoprotection", "fournitures de bureau", "fournitures scolaires", "mobilier scolaire", "mobilier de bureau", "produits d'entretien", "carburant", "medicament", "materiel medical", "transport scolaire", "rehabilitation", "renovation", "demolition", "desamiantage", "etancheite", "toiture", "plomberie", "chauffage", "climatisation", "ascenseur", "menuiserie", "voirie", "eclairage public", "assainissement", "eau potable", "dechets", "ordures", "espaces verts", "elagage", "cimetiere", "pompes funebres", "aide a domicile", "photographe"]

def motif(m):
    return r"\b" + r"s?\s+".join(re.escape(x) for x in m.split()) + r"s?\b"

def trouve(t, mots):
    t = simple(t)
    return [m for m in mots if re.search(motif(m), t)]

def texte(v):
    if isinstance(v, list):
        return " ".join(str(x) for x in v)
    return str(v or "")

def tout_texte(d):
    if isinstance(d, dict):
        return " ".join(tout_texte(v) for v in d.values())
    if isinstance(d, list):
        return " ".join(tout_texte(x) for x in d)
    return str(d) if isinstance(d, str) else ""

def titre_lot(d):
    if isinstance(d, dict):
        for k, v in d.items():
            c = simple(k)
            if any(x in c for x in ["intitule", "titre", "name", "objet"]) and isinstance(v, str):
                return v
        for v in d.values():
            t = titre_lot(v)
            if t:
                return t
    elif isinstance(d, list):
        for x in d:
            t = titre_lot(x)
            if t:
                return t
    return ""

# Trouve les lots dans les données détaillées de l'annonce
def chercher_lots(d, lots):
    if isinstance(d, dict):
        for k, v in d.items():
            if "lot" in simple(k):
                items = v if isinstance(v, list) else [v]
                for x in items:
                    if isinstance(x, dict) and len(x) == 1 and "lot" in simple(list(x)[0]):
                        chercher_lots(x, lots)
                    elif isinstance(x, (dict, list)):
                        txt = tout_texte(x)
                        if len(txt) > 20:
                            lots.append({"titre": titre_lot(x) or txt[:100], "texte": txt})
            else:
                chercher_lots(v, lots)
    elif isinstance(d, list):
        for x in d:
            chercher_lots(x, lots)

def donnees(a):
    d = a.get("donnees")
    if isinstance(d, str):
        try:
            d = json.loads(d)
        except Exception:
            d = None
    return d

def nombre(v):
    if isinstance(v, dict):
        v = v.get("#text") or v.get("value") or ""
    s = re.sub(r"[^\d,.]", "", str(v)).replace(",", ".")
    try:
        return float(s) if s else None
    except ValueError:
        return None

def chercher_montants(d, trouves):
    if isinstance(d, dict):
        for k, v in d.items():
            cle = simple(k)
            if "montant" in cle or "valeur" in cle:
                n = nombre(v)
                if n and n > 100:
                    trouves.append(n)
            chercher_montants(v, trouves)
    elif isinstance(d, list):
        for x in d:
            chercher_montants(x, trouves)

def montant(d):
    trouves = []
    chercher_montants(d, trouves)
    return max(trouves) if trouves else None

# 1. Récupérer les avis BOAMP des 7 derniers jours
depuis = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
params = urllib.parse.urlencode({"where": f"dateparution >= date'{depuis}'", "limit": -1})
url = "https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/exports/json?" + params
with urllib.request.urlopen(url, timeout=180) as r:
    avis = json.load(r)

# 2. Reprendre les annonces déjà triées par lot (les anciennes, non triées par lot, sont retirées)
liste = {}
try:
    with open("data.json", encoding="utf-8") as f:
        for a in json.load(f):
            if a.get("lots_fl") and not trouve(a.get("objet", ""), EXCLUSIONS):
                liste[a["id"]] = a
except Exception:
    pass

# 3. Trier les nouveaux avis, lot par lot
for a in avis:
    objet = texte(a.get("objet"))
    desc = texte(a.get("descripteur_libelle"))
    if trouve(objet, EXCLUSIONS):
        continue
    d = donnees(a)
    lots = []
    chercher_lots(d, lots)
    if not lots:
        lots = [{"titre": "Lot unique (non précisé)", "texte": objet + " " + desc + " " + tout_texte(d)}]
    # Lots où FL Structure a sa place
    lots_fl = [l for l in lots if trouve(l["texte"], STRUCTURE)]
    if not lots_fl:
        continue
    general = objet + " " + desc + " " + " ".join(l["texte"] for l in lots_fl)
    if not trouve(general, EVENEMENT):
        continue
    m = montant(d)
    if m is not None and m < SEUIL:
        continue
    liste[a.get("idweb")] = {
        "id": a.get("idweb"),
        "objet": objet,
        "acheteur": texte(a.get("nomacheteur")),
        "departement": texte(a.get("code_departement")),
        "parution": texte(a.get("dateparution")),
        "date_limite": texte(a.get("datelimitereponse")),
        "lien": texte(a.get("url_avis")),
        "mots": sorted(set(sum([trouve(l["texte"], STRUCTURE) for l in lots_fl], []))) + trouve(general, EVENEMENT),
        "lots_fl": [l["titre"][:150] for l in lots_fl],
        "montant": m,
        "statut": "sans montant" if m is None else "pertinent",
        "procedure": texte(a.get("procedure_libelle")),
        "famille": texte(a.get("famille_libelle")),
    }

# 4. Retirer les avis dont la date limite est passée
aujourdhui = datetime.date.today().isoformat()
garder = [a for a in liste.values() if not a["date_limite"] or a["date_limite"][:10] >= aujourdhui]
garder.sort(key=lambda a: (a["statut"] == "sans montant", a["date_limite"] or "9999"))

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(garder, f, ensure_ascii=False, indent=1)
print(len(garder), "appels d'offres gardés")
