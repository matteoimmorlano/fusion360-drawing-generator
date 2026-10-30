"""Tavola standard per qualsiasi pezzo: viste ortogonali + isometrica, scala automatica,
ingombri, fori riconosciuti dal modello, scheda di controllo, parametri di progetto e cartiglio."""
import math
import numpy as np
from tavola import projection_symbol, pick_scale, SCALES

# Codice eseguito in Fusion: ingombro, volume e fori (superfici cilindriche concave chiuse a 360°)
QUERY = r'''
_bodies = [b for b in root.bRepBodies if b.isLightBulbOn] or list(root.bRepBodies)
_mn = [1e9]*3; _mx = [-1e9]*3; _vol = 0
for _b in _bodies:
    _bb = _b.boundingBox; _vol += _b.volume
    for _i, (_a, _c) in enumerate(((_bb.minPoint.x, _bb.maxPoint.x), (_bb.minPoint.y, _bb.maxPoint.y), (_bb.minPoint.z, _bb.maxPoint.z))):
        _mn[_i] = min(_mn[_i], _a*10); _mx[_i] = max(_mx[_i], _c*10)
extra['bbox'] = _mn + _mx
extra['volume_cm3'] = _vol
_holes = []
for _b in _bodies:
    for _f in _b.faces:
        _g = _f.geometry
        if _g.surfaceType != adsk.core.SurfaceTypes.CylinderSurfaceType: continue
        _r = _g.radius*10
        if _r > 60: continue
        _ax = _g.axis; _ax.normalize(); _o = _g.origin
        _p = _f.pointOnFace; _ok, _n = _f.evaluator.getNormalAtPoint(_p)
        _v = _o.vectorTo(_p); _v.subtract(adsk.core.Vector3D.create(_ax.x*_v.dotProduct(_ax), _ax.y*_v.dotProduct(_ax), _ax.z*_v.dotProduct(_ax)))
        if _n.dotProduct(_v) >= 0: continue              # convessa: non e' un foro
        _sweep = 0
        for _e in _f.edges:
            _eg = _e.geometry
            if _eg is None: continue
            if _eg.curveType == adsk.core.Curve3DTypes.Circle3DCurveType and abs(_eg.radius*10 - _r) < 0.01: _sweep = 360
            elif _eg.curveType == adsk.core.Curve3DTypes.Arc3DCurveType and abs(_eg.radius*10 - _r) < 0.01:
                _sweep = max(_sweep, math.degrees(_eg.endAngle - _eg.startAngle))
        _c = _f.centroid
        _holes.append({'d': 2*_r, 'ax': [_ax.x, _ax.y, _ax.z], 'c': [_c.x*10, _c.y*10, _c.z*10], 'sweep': _sweep})
extra['fori'] = _holes
'''

VISTE = {"F": ((0, -1, 0), (1, 0, 0)), "T": ((0, 0, 1), (1, 0, 0)),
         "L": ((-1, 0, 0), (0, -1, 0)), "I": ((1, -1, 1), (1, 1, 0))}
# coordinate 2D di un punto 3D in ciascuna vista (come hlr.project)
TO2D = {"F": lambda p: (p[0], p[2]), "T": lambda p: (p[0], p[1]), "L": lambda p: (-p[1], p[2])}
AXIS = {"F": (0, 1, 0), "T": (0, 0, 1), "L": (1, 0, 0)}


def _merge_holes(raw):
    """Unisce le facce dello stesso foro (stesso asse e diametro) e scarta i raccordi (<300°)."""
    holes = []
    for h in raw:
        ax = np.array(h["ax"]); c = np.array(h["c"])
        for g in holes:
            if abs(g["d"] - h["d"]) < 0.02 and abs(abs(ax @ g["ax"]) - 1) < 1e-3:
                dv = c - g["c"]; perp = dv - (dv @ g["ax"]) * g["ax"]
                if np.linalg.norm(perp) < 0.05:
                    g["sweep"] += h["sweep"]; break
        else:
            holes.append({"d": h["d"], "ax": ax, "c": c, "sweep": h["sweep"]})
    return [h for h in holes if h["sweep"] >= 300]


def _visible(proj, c, r):
    """True se nella vista c'e' una circonferenza visibile di raggio r attorno a c (>=60%)."""
    pts = np.vstack(proj["visible"]); d = np.hypot(pts[:, 0] - c[0], pts[:, 1] - c[1])
    sel = pts[np.abs(d - r) < max(0.05 * r, 0.15)]
    if len(sel) < 8: return False
    ang = np.degrees(np.arctan2(sel[:, 1] - c[1], sel[:, 0] - c[0])) % 360
    return len(np.unique((ang // 15).astype(int))) >= 15


def _ext(proj):
    a = np.vstack(proj["visible"]); return a.min(0), a.max(0)


def _stxt(s):
    return f"{int(round(s))}:1" if s >= 1 else f"1:{int(round(1 / s))}"


def _hidden_circle(sh, c, r):
    pts = [(c[0] + r * math.cos(t), c[1] + r * math.sin(t)) for t in np.linspace(0, 2 * math.pi, 49)]
    sh.poly(pts, 0.18, dash=(2, 1))


def _tbox(knee, tw, right):
    """Ingombro del testo di un richiamo con la spalla che parte da knee."""
    x0 = knee[0] if right else knee[0] - tw
    return (x0 - 1, knee[1] - 2, x0 + tw + 1, knee[1] + 5)


def _overlap(p, q):
    return p[0] < q[2] and p[2] > q[0] and p[1] < q[3] and p[3] > q[1]


def _knee(c, r, tw, own, ostacoli, limiti):
    """Gomito del richiamo di un foro (centro c, raggio r sul foglio) con il testo fuori dalla vista:
    prova a destra, sinistra, sopra e sotto la vista e tiene il richiamo libero piu' corto."""
    x0, y0, x1, y1 = own
    cand = []
    for dy in (8, 0, 16, -8, 24, -16, 32, -24):
        cand += [((x1 + 2, c[1] + dy), True), ((x0 - 2, c[1] + dy), False)]
    for dx in (6, -6, 18, -18, 30, -30):
        cand += [((c[0] + dx, y1 + 3), dx > 0), ((c[0] + dx, y0 - 6), dx > 0)]
    best = (None, True); bl = 1e9
    for knee, right in cand:
        tb = _tbox(knee, tw, right)
        if tb[0] < limiti[0] or tb[1] < limiti[1] or tb[2] > limiti[2] or tb[3] > limiti[3]: continue
        if any(_overlap(tb, o) for o in ostacoli): continue
        L = math.hypot(knee[0] - c[0], knee[1] - c[1]) - r
        if L < bl: best, bl = (knee, right), L
    return best


def _inchiostro(proj, V, passo=0.8):
    """Punti (sul foglio) lungo tutte le linee di una vista, per non scriverci sopra."""
    pts = []
    for e in proj.get("visible", []) + proj.get("hidden", []):
        q = np.array([V(*p) for p in e])
        for a, b in zip(q[:-1], q[1:]):
            n = max(1, int(np.hypot(*(b - a)) / passo))
            pts.append(a + (b - a) * np.linspace(0, 1, n + 1)[:, None])
    return np.vstack(pts) if pts else np.zeros((0, 2))


def _knee_dentro(c, r, tw, ostacoli, limiti, ink):
    best = (None, True); bl = 1e9
    for ang in range(0, 360, 15):
        u = (math.cos(math.radians(ang)), math.sin(math.radians(ang)))
        for d in (8, 12, 16, 22, 30, 40):
            knee = (c[0] + (r + d) * u[0], c[1] + (r + d) * u[1]); right = u[0] >= 0
            tb = _tbox(knee, tw, right)
            if tb[0] < limiti[0] or tb[1] < limiti[1] or tb[2] > limiti[2] or tb[3] > limiti[3]: continue
            if any(_overlap(tb, o) for o in ostacoli): continue
            if len(ink) and np.any((ink[:, 0] > tb[0]) & (ink[:, 0] < tb[2]) & (ink[:, 1] > tb[1]) & (ink[:, 1] < tb[3])): continue
            if d < bl: best, bl = (knee, right), d
            break
    return best


class _Griglia:
    """Occupazione del foglio a passo 2 mm, per trovare dove mettere un riquadro libero."""
    def __init__(self, W, H, m, rects, step=2.0):
        self.s, self.ox, self.oy = step, m + 2, m + 2
        nx, ny = int((W - 2 * m - 4) / step), int((H - 2 * m - 4) / step)
        g = np.zeros((ny, nx), bool)
        for (a, b, c, d) in rects:
            i0, i1 = max(0, int((b - self.oy) / step)), min(ny, int(math.ceil((d - self.oy) / step)))
            j0, j1 = max(0, int((a - self.ox) / step)), min(nx, int(math.ceil((c - self.ox) / step)))
            if i0 < i1 and j0 < j1: g[i0:i1, j0:j1] = True
        self.I = np.pad(g.astype(int).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
        self.ny, self.nx = ny, nx

    def posto(self, w, h, vicino):
        """Angolo in basso a sinistra di un riquadro w x h libero, il piu' vicino al riquadro 'vicino'."""
        cw, ch = int(math.ceil(w / self.s)), int(math.ceil(h / self.s))
        if cw > self.nx or ch > self.ny: return None
        I = self.I
        occ = I[ch:, cw:] - I[:-ch, cw:] - I[ch:, :-cw] + I[:-ch, :-cw]
        ii, jj = np.nonzero(occ == 0)
        if not len(ii): return None
        x = self.ox + jj * self.s; y = self.oy + ii * self.s
        cx, cy = x + w / 2, y + h / 2
        dx = np.maximum(0, np.maximum(vicino[0] - cx, cx - vicino[2]))
        dy = np.maximum(0, np.maximum(vicino[1] - cy, cy - vicino[3]))
        k = np.argmin(np.hypot(dx, dy) * 1000 + np.hypot(cx - (vicino[0] + vicino[2]) / 2, cy - (vicino[1] + vicino[3]) / 2))
        return float(x[k]), float(y[k])


def disegna(sh, P, G, PJ, meta, cfg):
    X0, Y0, Z0, X1, Y1, Z1 = G["bbox"]
    DX, DY, DZ = X1 - X0, Y1 - Y0, Z1 - Z0
    fori = _merge_holes(G.get("fori", []))
    m = sh.m; W, H = sh.W, sh.H
    sh.frame(8, 6)

    # ---- contenuto delle tabelle (serve prima, per sapere quanto spazio occupano) ----
    groups = {}
    for h in fori: groups.setdefault(round(h["d"], 2), []).append(h)
    par = [(k, v) for k, v in P.items() if not k.startswith("calc_") and isinstance(v, (int, float))]
    npar = min(len(par), 12)
    n_checks = 3 + len(groups)
    RH = 5.2
    tab_bottom = H - m - RH * (n_checks + 4) - (4 + 4.4 * (npar + 1) if npar else 0) - 4
    TAB_X = W - m - 132                       # bordo sinistro scheda/parametri
    CART_X, CART_TOP = W - m - 195, m + 64    # cartiglio

    # ---- impaginazione: frontale in alto a sx, laterale a destra, dall'alto sotto (ISO-E) ----
    GH, GV, X_L, BOT = 26, 30, 22, m + 4
    def boxes(S, TOP):
        wF, hF, wL, hT = S * DX, S * DZ, S * DY, S * DY
        F_ = (X_L, TOP - hF, X_L + wF, TOP)
        L_ = (X_L + wF + GH, TOP - hF, X_L + wF + GH + wL, TOP)
        T_ = (X_L, TOP - hF - GV - hT, X_L + wF, TOP - hF - GV)
        return F_, L_, T_
    def ok(S, TOP):
        F_, L_, T_ = boxes(S, TOP)
        if T_[1] < BOT: return False
        for b, margin in ((F_, 16), (L_, 2)):
            right = b[2] + margin
            limit = TAB_X - 4 if b[1] < H - m and b[3] > tab_bottom else W - m - 2
            if right > limit: return False
        if T_[2] + 2 > CART_X - 4 and T_[1] < CART_TOP + 4: return False
        return True
    cand = sorted([sc for sc in SCALES if sc[0] <= 5], key=lambda t: -t[0])
    # due impaginazioni: viste in alto (accanto alle tabelle) o abbassate sotto le tabelle
    tops = (266, min(266, tab_bottom - 18))
    S, TOP = next(((sc[0], t) for sc in cand for t in tops if ok(sc[0], t)), (cand[-1][0], 266)); ST = _stxt(S)
    Fb, Lb, Tb = boxes(S, TOP)

    F = sh.view(PJ["F"], Fb[0] - S * X0, Fb[1] - S * Z0, S, "Vista frontale", ST, (Fb[0], TOP + 14))
    L = sh.view(PJ["L"], Lb[0] + S * Y1, Lb[1] - S * Z0, S, "Vista laterale sinistra", ST, (Lb[0], TOP + 14))
    T = sh.view(PJ["T"], Tb[0] - S * X0, Tb[1] - S * Y0, S, "Vista dall'alto", ST, (Tb[0], Tb[3] + 9))
    VIEWS = {"F": F, "T": T, "L": L}
    # ingombri (con quote e titoli) da non coprire con i richiami dei fori e l'isometrica
    BOX = {"F": (Fb[0] - 4, Fb[1] - 16, Fb[2] + 18, Fb[3] + 18), "L": (Lb[0] - 4, Lb[1] - 16, Lb[2] + 6, Lb[3] + 18),
           "T": (Tb[0] - 4, Tb[1] - 6, Tb[2] + 6, Tb[3] + 16)}
    ostacoli = list(BOX.values()) + [(TAB_X - 3, tab_bottom, W - m, H - m), (CART_X - 3, m, W - m, CART_TOP + 3)]
    vista = (min(B[0] for B in BOX.values()), min(B[1] for B in BOX.values()),
             max(B[2] for B in BOX.values()), max(B[3] for B in BOX.values()))

    checks = []
    def chk(name, val):
        checks.append((name, val)); return len(checks)

    # ---- quote d'ingombro ----
    sh.hdim(F(X0, Z0), F(X1, Z0), F(0, Z0)[1] - 9, f"{DX:.2f}", balloon=chk("Lunghezza totale (X)", f"{DX:.2f} ±0.25"))
    sh.vdim(F(X1, Z0), F(X1, Z1), F(X1, 0)[0] + 9, f"{DZ:.2f}", balloon=chk("Altezza totale (Z)", f"{DZ:.2f} ±0.25"),
            text_side="u" if Fb[3] + 38 < sh.H - m else "d")
    sh.hdim(L(-Y1, Z0), L(-Y0, Z0), L(0, Z0)[1] - 9, f"{DY:.2f}", balloon=chk("Larghezza totale (Y)", f"{DY:.2f} ±0.25"))

    # ---- fori: richiamo nella vista lungo l'asse; se il foro non si vede, cerchio tratteggiato ----
    used = {"F": 0, "T": 0, "L": 0}
    for d, hs in sorted(groups.items()):
        n = len(hs); txt = f"{n}x Ø{d:.2f}" if n > 1 else f"Ø{d:.2f}"
        par_views = [k for k in ("T", "F", "L") if abs(np.array(AXIS[k]) @ hs[0]["ax"]) > 0.98]
        vis = [k for k in par_views if _visible(PJ[k], TO2D[k](hs[0]["c"]), d / 2)]
        v = (vis or par_views or [None])[0]
        name = f"Diametro fori {n}x" if n > 1 else "Diametro foro"
        if v is None:
            chk(name + " (vedi STEP)", f"Ø{d:.2f} ±0.25"); continue
        num = chk(name + ("" if vis else " (nascosti)"), f"Ø{d:.2f} ±0.25")
        V = VIEWS[v]; r = d / 2
        for h in hs:
            c2 = TO2D[v](h["c"])
            if not vis: _hidden_circle(sh, V(*c2), r * S)
            sh.center_mark(V(*c2), r * S)
        cx, cy = TO2D[v](hs[0]["c"])
        cs = V(cx, cy)
        tw = sh.tw(txt) + sh.tw("±0.25", 2.5 * 0.62) + 13          # testo + tolleranza + pallino
        lim = (m + 2, m + 2, W - m - 2, H - m - 2)
        knee, right = _knee(cs, r * S, tw, BOX[v], ostacoli, lim)
        if knee is None:                                          # fuori non c'e' posto: dentro la vista, lontano dalle linee
            knee, right = _knee_dentro(cs, r * S, tw, [o for o in ostacoli if o != BOX[v]], lim, _inchiostro(PJ[v], V))
        if knee is None:                                          # nessun posto libero: come prima
            k = used[v]; used[v] += 1
            pon = V(cx + r * 0.707, cy + r * 0.707); knee, right = (pon[0] + 8 + 4 * k, pon[1] + 9 + 7 * k), True
        u = np.subtract(knee, cs); u = u / (np.linalg.norm(u) or 1)
        pon = (cs[0] + r * S * u[0], cs[1] + r * S * u[1])
        sh.leader(pon, knee, txt, "±0.25", balloon=num, right=right)
        ostacoli.append(_tbox(knee, tw, right))

    # ---- isometrica: la scala piu' grande che entra nello spazio libero, vicino alle altre viste ----
    a, b = _ext(PJ["I"]); iw, ih = b - a
    grid = _Griglia(W, H, m, ostacoli)
    best = None
    for si in [sc[0] for sc in cand if sc[0] <= 2.5 * S + 1e-9]:
        pos = grid.posto(si * iw + 4, si * ih + 18, vista)        # +18: titolo e scala sopra
        if pos:
            best = (si, pos); break
    if best:
        si, (x0, y0) = best
        cxI, cyI = x0 + 2 + si * iw / 2, y0 + 2 + si * ih / 2
        sh.view(PJ["I"], cxI - si * (a[0] + b[0]) / 2, cyI - si * (a[1] + b[1]) / 2, si,
                "Vista isometrica", _stxt(si), (cxI - si * iw / 2, cyI + si * ih / 2 + 12))

    # ---- scheda operativa di controllo (alto a destra) ----
    cw = [12, 54, 36, 30]
    rows = [[("*SCHEDA OPERATIVA DI CONTROLLO", 4)], [("CARATTERISTICHE DA CONTROLLARE", 3), "ESITO"],
            ["*N°", "*CARATTERISTICA", "*NOMINALE", "*RILEVATO"]]
    rows += [[str(i + 1), x, y, ""] for i, (x, y) in enumerate(checks)]
    rows += [[("CONTROLLATO DA", 2), "DATA", ""]]
    sh.table(TAB_X, H - m, cw, RH, rows, h=2.4)
    y_after = H - m - RH * len(rows) - 4

    # ---- parametri di progetto (sotto la scheda) ----
    if npar:
        prow = [[("*PARAMETRI DI PROGETTO", 2)]]
        for k, v in par[:npar]:
            prow.append([k.replace("_", " "), f"{v:.2f}"])
        if len(par) > npar: prow[-1] = ["...", f"(+{len(par) - npar + 1} nel modello)"]
        sh.table(TAB_X, y_after, [96, 36], 4.4, prow, h=2.2)

    # cartiglio (basso a destra)
    tbw = 195; xt = W - m - tbw; yt = m + 64
    sh.table(xt, yt, [145, 50], 12, [["*" + cfg.get("intestazione", "").upper(), ""]], h=4.5)
    projection_symbol(sh, xt + 170, yt - 6, True, 0.75)
    y2 = yt - 12; rh = 6.5; th = 2.3
    massa = G["volume_cm3"] * cfg.get("densita", 1.27)
    sh.table(xt, y2, [55], rh, [["*REQUISITI TECNICI"], [f"Massa: ~{massa:.0f} g (pieno)"], ["Unita' di misura: mm"],
                                ["Toll. generali: ±0.25"], ["Quote non indicate:"], ["vedi modello STEP"],
                                [f"Fabbricazione: {cfg.get('fabbricazione', 'FDM')}"], [cfg.get("nota", "")]], h=th)
    sh.table(xt + 55, y2, [26, 22], rh, [["Disegnato", "Data"], ["*" + cfg.get("autore", ""), "*" + meta["data"]],
                                          ["Controllato", "Data"], ["", ""], ["Approvato", "Data"], ["", ""],
                                          ["Proiezione", "Formato"], ["*ISO-E", "*A3"]], h=th)
    sh.table(xt + 103, y2, [34, 58], rh, [["Revisione", "*" + meta["rev"]], ["Descrizione", meta["descrizione"]],
                                           ["Scala", f"*{ST}"], ["Foglio", "*1 di 1"],
                                           [("Titolo", 2)], [("*" + cfg.get("titolo", cfg["documento"]).upper(), 2)],
                                           ["N. disegno", "*" + cfg.get("numero", cfg["documento"]).upper()],
                                           ["Materiale", "*" + cfg.get("materiale", "PETG")]], h=th)
