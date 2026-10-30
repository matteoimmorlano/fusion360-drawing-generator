#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "cadquery-ocp==8.0.1.1.0", "reportlab"]
# ///
"""Genera la tavola tecnica A3 di un pezzo leggendo i dati dal design aperto in Fusion 360.

Parla direttamente con l'add-in Fusion360MCP (socket localhost:9876), quindi non serve Claude.
Fusion deve essere aperto, con l'add-in avviato e un design 3D in primo piano
(il documento del pezzo puo' stare in un'altra scheda, ma deve essere aperto).

Di norma si usa il pulsante "Genera tavola" dell'add-in TavolaTecnica (addin/), che chiama --dati.

Uso da terminale:
    tavola_fusion.py CARTELLA_PROGETTO [--rev B] [--descrizione "..."] [--out file.pdf]
    tavola_fusion.py --dati dati.json              usato dall'add-in TavolaTecnica (dati gia' letti da Fusion)

tavola.json (nella cartella del progetto):
    documento      nome del documento Fusion (obbligatorio)
    nome_file      base del nome del PDF (default = documento)
    titolo, numero, materiale, densita (g/cm3), fabbricazione, nota   -> cartiglio
    ricetta        (opzionale) file in ricette/ con viste e quote su misura; senza = tavola standard
"""
import argparse, datetime, importlib.util, json, os, shutil, socket, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

HOST, PORT = os.environ.get("FUSION_MCP_HOST", "localhost"), int(os.environ.get("FUSION_MCP_PORT", "9876"))

FETCH = r'''
import json, math, adsk.core, adsk.fusion
_doc = [d for d in app.documents if d.name == {doc!r}]
if not _doc:
    raise RuntimeError("Documento non aperto in Fusion: " + {doc!r})
des = adsk.fusion.Design.cast(_doc[0].products.itemByProductType('DesignProductType'))
root = des.rootComponent
P = {{}}
for _i in range(des.userParameters.count):
    _p = des.userParameters.item(_i)
    if _p.unit == 'mm': P[_p.name] = _p.value * 10
    elif _p.unit == 'deg': P[_p.name] = math.degrees(_p.value)
    elif _p.unit == '': P[_p.name] = _p.value
extra = {{}}
{query}
_vis = [(m, m.isLightBulbOn) for m in root.meshBodies]
for m, _ in _vis: m.isLightBulbOn = False
_ok = des.exportManager.execute(des.exportManager.createSTEPExportOptions({step!r}, root))
for m, v in _vis: m.isLightBulbOn = v
json.dumps({{"P": P, "G": extra, "step_ok": _ok}})
'''

def fusion(code):
    try:
        s = socket.create_connection((HOST, PORT), timeout=10)
    except OSError:
        raise SystemExit("Fusion non risponde: apri Fusion 360 e avvia l'add-in Fusion360MCP.")
    s.sendall((json.dumps({"type": "execute_code", "params": {"code": code}}) + "\n").encode())
    s.settimeout(120)
    buf = b""
    while b"\n" not in buf:
        chunk = s.recv(65536)
        if not chunk: break
        buf += chunk
    s.close()
    resp = json.loads(buf.split(b"\n", 1)[0])
    if resp.get("status") == "error":
        msg = resp.get("message", "?")
        if "No active design" in msg:
            msg = "porta in primo piano un design 3D in Fusion (non una tavola o la pagina iniziale)"
        raise SystemExit("Errore da Fusion: " + msg)
    res = resp.get("result", {})
    val = res.get("result", res) if isinstance(res, dict) else res
    return json.loads(val) if isinstance(val, str) else val


def carica_ricetta(cfg):
    if cfg.get("ricetta"):
        p = cfg["ricetta"] if os.path.isabs(cfg["ricetta"]) else os.path.join(HERE, "ricette", cfg["ricetta"])
        spec = importlib.util.spec_from_file_location("ricetta", p)
        R = importlib.util.module_from_spec(spec); spec.loader.exec_module(R)
        return R
    import generico
    return generico


def genera(cfg, data, step, rev, descrizione, out, R=None):
    R = R or carica_ricetta(cfg)
    print("2/3  Calcolo viste (rimozione linee nascoste)...", flush=True)
    from hlr import load_step, project
    from polyhlr import project_poly
    shp = load_step(step)
    viste = R.VISTE(data["P"]) if callable(R.VISTE) else R.VISTE
    PJ = {}
    for k, (vd, xd) in viste.items():
        p = project(shp, vd, xd)
        if not p["visible"]:
            p = project_poly(shp, vd, xd)
        PJ[k] = p

    os.makedirs(os.path.dirname(out), exist_ok=True)
    print("3/3  Disegno tavola...", flush=True)
    from tavola import Sheet
    sh = Sheet(out, "A3", txt=2.5)
    meta = {"rev": rev, "descrizione": descrizione, "data": datetime.date.today().strftime("%d/%m/%Y")}
    import inspect
    if len(inspect.signature(R.disegna).parameters) >= 6:
        R.disegna(sh, data["P"], data["G"], PJ, meta, cfg)
    else:
        R.disegna(sh, data["P"], data["G"], PJ, meta)
    sh.save()
    print("Fatto:", out, flush=True)


def main():
    ap = argparse.ArgumentParser(description="Tavola tecnica A3 da Fusion 360")
    ap.add_argument("progetto", nargs="?", help="cartella del progetto (con tavola.json)")
    ap.add_argument("--dati", help="JSON scritto dall'add-in: cfg, P, G, step, rev, descrizione, out")
    ap.add_argument("--rev", default="A")
    ap.add_argument("--descrizione", default="Prima emissione")
    ap.add_argument("--out")
    ap.add_argument("--apri", action="store_true", help="apri il PDF alla fine")
    a = ap.parse_args()
    if a.dati:
        d = json.load(open(a.dati, encoding="utf-8"))
        genera(d["cfg"], d, d["step"], d["rev"], d["descrizione"], d["out"])
        return
    if not a.progetto:
        ap.error("serve la cartella del progetto (oppure --dati)")

    cfg_path = os.path.join(a.progetto, "tavola.json")
    if not os.path.exists(cfg_path):
        raise SystemExit(f"Manca {cfg_path} (oppure usa il pulsante Genera tavola in Fusion)")
    cfg = json.load(open(cfg_path))
    R = carica_ricetta(cfg)

    tmp = tempfile.mkdtemp(prefix="tavola_")
    nome = cfg.get("nome_file", cfg["documento"])
    step = os.path.join(tmp, nome + ".step")
    print(f"1/3  Lettura parametri ed export STEP da Fusion ({cfg['documento']})...")
    data = fusion(FETCH.format(doc=cfg["documento"], query=R.QUERY, step=step))
    if not data.get("step_ok") or not os.path.exists(step):
        raise SystemExit("Export STEP non riuscito.")
    out = a.out or os.path.join(a.progetto, "03_Disegno_tecnico", f"{nome}_tavola_A3_rev{a.rev}.pdf")
    genera(cfg, data, step, a.rev, a.descrizione, out, R)
    shutil.rmtree(tmp, ignore_errors=True)
    if a.apri:
        os.system(f'open "{out}"')


if __name__ == "__main__":
    main()
