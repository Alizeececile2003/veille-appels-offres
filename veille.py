import json, re, datetime, unicodedata, urllib.request, urllib.parse
from collections import Counter

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

# Codes CPV du métier : échafaudage (travaux), échafaudages (matériel),
# structures préfabriquées, scènes, bâtiments préfabriqués
CPV_METIER = {"45262100", "44212310", "45223800", "45237000", "44211000"}

# Plateformes où l'on télécharge les dossiers de consultation
PLATEFORMES = ["marches-publics", "achatpublic", "maximilien", "megalis",
               "e-marchespublics", "marches-securises", "klekoon", "synapse",
               "ternum", "francemarches", "dematis", "awsolutions", "atexo",
               "local-trust", "marchespublics", "mpe", "salle-des-marches"]

# Noms lisibles des plateformes (pour compter les plus fréquentes)
NOMS_PLATEFORMES = [("marches-publics.gouv.fr", "PLACE"),
                    ("achatpublic", "AchatPublic"),
                    ("maximilien", "Maximilien"),
                    ("megalis", "Mégalis"),
                    ("e-marchespublics", "e-marchespublics"),
                    ("marches-securises", "Marchés sécurisés"),
                    ("klekoon", "Klekoon"),
                    ("synapse", "Synapse"),
                    ("ternum", "Ternum"),
                    ("francemarches", "France Marchés"),
                    ("dematis", "Dematis"),
                    ("awsolutions", "AWS"),
                    ("local-trust", "Local Trust"),
                    ("salle-des-marches", "Salle des marchés")]

# Signes qu'un lien mène directement à la consultation (et pas à l'accueil)
SIGNES_LIEN_DIRECT = ["refconsultation", "/consultation/", "detailsconsultation",
                      "idconsultation", "id_consultation", "consultation_id"]

def plateforme(u):
    ul = str(u or "").lower()
    if not ul:
        return "non indiquée"
    for cle, nom in NOMS_PLATEFORMES:
        if cle in ul:
            return nom
    m = re.match(r"https?://(?:www\.)?([^/]+)", ul)
    return m.group(1) if m else "non indiquée"

def lien_direct(u):
    ul = str(u or "").lower()
    return any(s in ul for s in SIGNES_LIEN_DIRECT)

# Récupère les codes CPV présents dans les données de l'annonce
def chercher_cpv(d, codes, dans_cpv=False):
    if isinstance(d, dict):
        for k, v in d.items():
            cle = simple(k)
            chercher_cpv(v, codes, dans_cpv or "cpv" in cle or "classification" in cle)
    elif isinstance(d, list):
        for x in d:
            chercher_cpv(x, codes, dans_cpv)
    elif dans_cpv:
        codes.update(re.findall(r"\b\d{8}\b", str(d)))

# Récupère tous les liens internet présents dans les données de l'annonce
def chercher_urls(d, urls, chemin=""):
    if isinstance(d, dict):
        for k, v in d.items():
            chercher_urls(v, urls, chemin + " " + simple(k))
    elif isinstance(d, list):
        for x in d:
            chercher_urls(x, urls, chemin)
    elif isinstance(d, str):
        for u in re.findall(r"(?:https?://|www\.)[^\s\"'<>]+", d):
            u = u.rstrip(".,;)")
            if u.lower().startswith("www."):
                u = "https://" + u
            urls.append((chemin, u))

# Choisit le lien le plus probable vers le dossier de consultation
# (un lien direct vers la consultation passe avant la page d'accueil)
def dossier(d):
    urls = []
    chercher_urls(d, urls)
    meilleur, score_max = "", 0
    for chemin, u in urls:
        ul = u.lower()
        if "boamp.fr" in ul or "europa.eu" in ul:
            continue
        c = chemin + " " + simple(u)
        s = 0
        for mot, points in [("document", 3), ("dce", 3), ("consultation", 2),
                            ("profil", 2), ("acheteur", 1), ("acces", 1), ("url", 1)]:
            if mot in c:
                s += points
        if any(p in ul for p in PLATEFORMES):
            s += 3
        if lien_direct(u):
            s += 5
        if s > score_max:
            meilleur, score_max = u, s
    return meilleur if score_max >= 2 else ""

# Récupère la référence INTERNE du marché donnée par l'acheteur
# (celle qu'on tape dans la recherche de sa plateforme)
CLES_REF_FORTES = ["ref_marche", "refmarche", "reference_marche", "referencemarche",
                   "reference_interne", "ref_interne", "internalid",
                   "reference_consultation", "ref_consultation",
                   "numero_marche", "num_marche", "numero_consultation"]

def ref_valide(v, idweb):
    v = str(v).strip().strip(".,;:")
    if not (2 < len(v) < 60):
        return ""
    if idweb and v == str(idweb):
        return ""
    if re.fullmatch(r"\d{2}-\d{4,7}", v):      # identifiant BOAMP
        return ""
    if re.fullmatch(r"\d{8}(-\d)?", v):        # code CPV
        return ""
    if "http" in v.lower() or "www." in v.lower() or "@" in v:
        return ""
    if len(v.split()) > 6:                     # une phrase, pas une référence
        return ""
    return v

def reference(d, idweb=""):
    candidats = []   # (priorité, valeur) : plus la priorité est basse, mieux c'est

    def ajouter(prio, v):
        v = ref_valide(v, idweb)
        if v:
            candidats.append((prio, v))

    def fouiller(x, chemin):
        if isinstance(x, dict):
            # Format européen eForms : identifiant interne marqué "InternalID"
            schema = simple(x.get("@schemeName", "") or x.get("schemeName", ""))
            if "internal" in schema:
                ajouter(0, x.get("#text") or x.get("value") or "")
            for k, v in x.items():
                cle = simple(k)
                if isinstance(v, (str, int)) and str(v).strip():
                    if any(m in cle for m in CLES_REF_FORTES):
                        ajouter(1, v)
                    elif cle in ("cbc:id", "id") and "procurementproject" in chemin:
                        ajouter(1, v)
                    elif "reference" in cle and "avis" not in cle and "bulletin" not in cle:
                        ajouter(2, v)
                fouiller(v, chemin + " " + cle)
        elif isinstance(x, list):
            for y in x:
                fouiller(y, chemin)

    fouiller(d, "")

    # Dernier recours : chercher "Référence : XXX" dans le texte de l'annonce
    txt = tout_texte(d)
    for m in re.finditer(
            r"r[ée]f[ée]rences?(?:\s+(?:du\s+march[ée]|de\s+la\s+consultation|interne|acheteur|de\s+l'acheteur))?\s*(?:n°|:)\s*([A-Za-z0-9][A-Za-z0-9/_.\-]{2,40})",
            txt, re.I):
        ajouter(3, m.group(1))

    if not candidats:
        return ""
    candidats.sort(key=lambda c: c[0])
    return candidats[0][1]

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
    # Codes CPV : si l'annonce en a, au moins un doit être du métier
    cpv = set()
    chercher_cpv(d, cpv)
    if cpv and not cpv & CPV_METIER:
        continue
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
    lien_dossier = dossier(d)
    liste[a.get("idweb")] = {
        "id": a.get("idweb"),
        "objet": objet,
        "acheteur": texte(a.get("nomacheteur")),
        "departement": texte(a.get("code_departement")),
        "parution": texte(a.get("dateparution")),
        "date_limite": texte(a.get("datelimitereponse")),
        "lien": texte(a.get("url_avis")),
        "dossier": lien_dossier,
        "plateforme": plateforme(lien_dossier),
        "lien_direct": lien_direct(lien_dossier),
        "reference": reference(d, a.get("idweb")),
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

# 5. Compter les plateformes (pour choisir les prochaines à ajouter)
compte = Counter(a.get("plateforme", "non indiquée") for a in garder)
for nom, n in compte.most_common():
    print("Plateforme :", nom, "-", n, "annonce(s)")
print("Liens directs :", sum(1 for a in garder if a.get("lien_direct")), "sur", len(garder))
