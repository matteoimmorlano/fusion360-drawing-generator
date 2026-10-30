"""Logica dell'add-in senza interfaccia: dati del cartiglio salvati nel design, lettura
parametri/geometria, export STEP e lancio in background del motore tavola_fusion.py."""
import ast, json, math, os, shutil, subprocess, tempfile, threading
import adsk.core, adsk.fusion

TOOL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))   # radice del repo
TOOL = os.path.join(TOOL_DIR, "tavola_fusion.py")
RICETTE = os.path.join(TOOL_DIR, "ricette")
PROGETTI = next(p for p in map(os.path.expanduser, ("~/Desktop/Progetti", "~/Documents", "~")) if os.path.isdir(p))
PREFS = os.path.expanduser("~/Library/Application Support/fusion360-drawing-generator/prefs.json")
UV = [os.path.expanduser(p) for p in ("/opt/homebrew/bin/uv", "~/.local/bin/uv", "/usr/local/bin/uv")]
GRUPPO, CHIAVE = "TavolaTecnica", "config"
DEFAULT = {"intestazione": "", "autore": "",
           "titolo": "", "numero": "", "nome_file": "", "materiale": "PETG", "densita": 1.27,
           "fabbricazione": "FDM", "nota": "", "ricetta": "", "cartella": "",
           "rev": "A", "descrizione": "Prima emissione"}


def design(doc):
    return adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType"))


def cerca_tavola_json(nome, radice=PROGETTI, prof=4):
    """tavola.json creato col vecchio --init per questo documento (solo per importarlo)."""
    for dirpath, dirs, files in os.walk(radice):
        dirs[:] = [] if dirpath[len(radice):].count(os.sep) >= prof else [d for d in dirs if not d.startswith(".")]
        if "tavola.json" in files:
            p = os.path.join(dirpath, "tavola.json")
            try:
                if json.load(open(p, encoding="utf-8")).get("documento") == nome:
                    return p
            except Exception:
                pass
    return None


def leggi_config(doc):
    """(cfg, origine): origine = 'documento', il percorso del tavola.json importato, oppure None."""
    n = doc.name
    cfg = dict(DEFAULT, titolo=n.replace("_", " "), numero=n, nome_file=n, **leggi_prefs())
    a = design(doc).attributes.itemByName(GRUPPO, CHIAVE)
    if a:
        cfg.update(json.loads(a.value))
        return cfg, "documento"
    old = cerca_tavola_json(n)
    if old:
        cfg.update({k: v for k, v in json.load(open(old, encoding="utf-8")).items() if k != "documento"})
        cfg["cartella"] = os.path.dirname(old)
    return cfg, old


def salva_config(doc, cfg):
    design(doc).attributes.add(GRUPPO, CHIAVE, json.dumps(cfg, ensure_ascii=False))
    os.makedirs(os.path.dirname(PREFS), exist_ok=True)
    json.dump({k: cfg[k] for k in ("intestazione", "autore")}, open(PREFS, "w", encoding="utf-8"), ensure_ascii=False)


def leggi_prefs():
    """Intestazione e autore dell'ultima tavola: valgono per tutti i pezzi nuovi."""
    try:
        return json.load(open(PREFS, encoding="utf-8"))
    except Exception:
        return {}


def ricette():
    return sorted(f for f in os.listdir(RICETTE) if f.endswith(".py")) if os.path.isdir(RICETTE) else []


def query(cfg):
    """Il testo QUERY della ricetta (o di generico.py, se la ricetta non ne ha una sua),
    letto senza importare il modulo."""
    for f in ([os.path.join(RICETTE, cfg["ricetta"])] if cfg.get("ricetta") else []) + [os.path.join(TOOL_DIR, "generico.py")]:
        for n in ast.parse(open(f, encoding="utf-8").read()).body:
            if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "QUERY" for t in n.targets):
                return ast.literal_eval(n.value)
    raise RuntimeError("QUERY non trovata")


def percorso_pdf(cfg):
    return os.path.join(cfg["cartella"], "03_Disegno_tecnico", f"{cfg['nome_file']}_tavola_A3_rev{cfg['rev']}.pdf")


def leggi_dati(doc, cfg, step):
    """Parametri utente (mm/deg) + dati della QUERY; esporta lo STEP senza le mesh."""
    des = design(doc)
    root = des.rootComponent
    P = {}
    for i in range(des.userParameters.count):
        p = des.userParameters.item(i)
        if p.unit == "mm": P[p.name] = p.value * 10
        elif p.unit == "deg": P[p.name] = math.degrees(p.value)
        elif p.unit == "": P[p.name] = p.value
    extra = {}
    exec(query(cfg), {"adsk": adsk, "math": math, "json": json, "app": adsk.core.Application.get(),
                      "des": des, "root": root, "P": P, "extra": extra})
    vis = [(m, m.isLightBulbOn) for m in root.meshBodies]
    try:
        for m, _ in vis: m.isLightBulbOn = False
        ok = des.exportManager.execute(des.exportManager.createSTEPExportOptions(step, root))
    finally:
        for m, v in vis: m.isLightBulbOn = v
    if not ok or not os.path.exists(step):
        raise RuntimeError("Export STEP non riuscito.")
    return P, extra


def avvia(cfg, P, G, step, out, al_termine):
    """Lancia tavola_fusion.py --dati in background; al_termine(ok, out, log) da un altro thread."""
    uv = next((u for u in UV if os.path.exists(u)), None)
    if not uv:
        raise RuntimeError("uv non trovato (installalo con: brew install uv)")
    tmp = os.path.dirname(step)
    dati = os.path.join(tmp, "dati.json")
    json.dump({"cfg": cfg, "P": P, "G": G, "step": step, "out": out,
               "rev": cfg["rev"], "descrizione": cfg["descrizione"]}, open(dati, "w", encoding="utf-8"), ensure_ascii=False)
    log = os.path.join(tmp, "log.txt")
    env = dict(os.environ, PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:" + os.environ.get("PATH", ""))
    env.pop("PYTHONHOME", None); env.pop("PYTHONPATH", None)   # non ereditare il Python di Fusion
    env["PYTHONUTF8"] = "1"
    with open(log, "w", encoding="utf-8") as fh:
        pr = subprocess.Popen([uv, "run", "--script", TOOL, "--dati", dati], stdout=fh, stderr=subprocess.STDOUT,
                              stdin=subprocess.DEVNULL, cwd=TOOL_DIR, env=env)

    def attendi():
        rc = pr.wait()
        testo = open(log, encoding="utf-8", errors="replace").read()
        shutil.rmtree(tmp, ignore_errors=True)
        al_termine(rc == 0 and os.path.exists(out), out, testo)
    threading.Thread(target=attendi, daemon=True).start()


def notifica(testo, titolo="Tavola tecnica"):
    subprocess.Popen(["osascript", "-e", f"display notification {json.dumps(testo)} with title {json.dumps(titolo)}"])


def nuova_cartella_temp():
    return tempfile.mkdtemp(prefix="tavola_")
