"""Technical drawing sheet in the 'scheda operativa' style (zoned frame, inspection table,
title block, monospace font, dimensions with ± tolerance). All coordinates in mm, origin
bottom-left of the sheet."""
import math
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

pdfmetrics.registerFont(TTFont("Mono", "/System/Library/Fonts/Menlo.ttc", subfontIndex=0))
pdfmetrics.registerFont(TTFont("MonoB", "/System/Library/Fonts/Menlo.ttc", subfontIndex=1))

SHEETS = {"A4": (297, 210), "A3": (420, 297), "A2": (594, 420), "A1": (841, 594)}
LW_FRAME, LW_VIS, LW_THIN = 0.5, 0.35, 0.18
TXT = 3.5          # dimension text height (mm)
ARROW = (3.0, 0.6)  # arrow length, half width (mm)


# ISO 5455 scales, preferred order when choosing the one that fits the sheet
SCALES = [(1, "1:1"), (2, "2:1"), (0.5, "1:2"), (5, "5:1"), (0.2, "1:5"), (10, "10:1"), (0.1, "1:10")]


def pick_scale(extent_mm, room_mm):
    """Largest ISO 5455 scale at which a view of size extent_mm (w, h) fits room_mm (w, h)."""
    fits = [(s, t) for s, t in SCALES if extent_mm[0] * s <= room_mm[0] and extent_mm[1] * s <= room_mm[1]]
    return max(fits, key=lambda f: f[0]) if fits else min(SCALES, key=lambda f: f[0])


class Sheet:
    def __init__(self, path, size="A3", margin=12, txt=3.5):
        global TXT
        TXT = txt
        self.W, self.H = SHEETS[size]
        self.size = size
        self.m = margin
        self.c = canvas.Canvas(path, pagesize=(self.W * mm, self.H * mm))
        self.c.setLineCap(1); self.c.setLineJoin(1)

    # ---- primitives -------------------------------------------------------
    def lw(self, w): self.c.setLineWidth(w * mm)
    def line(self, x1, y1, x2, y2, w=LW_THIN):
        self.lw(w); self.c.line(x1 * mm, y1 * mm, x2 * mm, y2 * mm)
    def rect(self, x, y, w, h, lw=LW_THIN, fill=0):
        self.lw(lw); self.c.rect(x * mm, y * mm, w * mm, h * mm, stroke=1, fill=fill)
    def poly(self, pts, w=LW_VIS, dash=None):
        self.lw(w)
        if dash: self.c.setDash([d * mm for d in dash])
        p = self.c.beginPath(); p.moveTo(pts[0][0] * mm, pts[0][1] * mm)
        for x, y in pts[1:]: p.lineTo(x * mm, y * mm)
        self.c.drawPath(p, stroke=1, fill=0)
        if dash: self.c.setDash([])
    def text(self, x, y, s, h=None, font="Mono", anchor="l", rot=0):
        h = h or TXT
        pt = h * 2.835 * 1.25  # nominal text height (mm) -> font size (pt)
        w = pdfmetrics.stringWidth(s, font, pt) / mm
        self.c.saveState(); self.c.translate(x * mm, y * mm); self.c.rotate(rot)
        dx = {"l": 0, "c": -w / 2, "r": -w}[anchor]
        self.c.setFont(font, pt); self.c.drawString(dx * mm, 0, s); self.c.restoreState()
        return w
    def tw(self, s, h=None, font="Mono"):
        h = h or TXT
        return pdfmetrics.stringWidth(s, font, h * 2.835 * 1.25) / mm
    def arrow(self, x, y, ang):
        L, hw = ARROW; ca, sa = math.cos(ang), math.sin(ang)
        bx, by = x - L * ca, y - L * sa
        p = self.c.beginPath(); p.moveTo(x * mm, y * mm)
        p.lineTo((bx - hw * sa) * mm, (by + hw * ca) * mm); p.lineTo((bx + hw * sa) * mm, (by - hw * ca) * mm); p.close()
        self.c.drawPath(p, stroke=0, fill=1)

    # ---- frame ------------------------------------------------------------
    def frame(self, hz=12, vz=8):
        m, W, H = self.m, self.W, self.H
        self.rect(m, m, W - 2 * m, H - 2 * m, LW_FRAME)
        self.rect(m / 2, m / 2, W - m, H - m, LW_THIN)
        cw, ch = (W - 2 * m) / hz, (H - 2 * m) / vz
        for i in range(hz):
            x = m + (i + 0.5) * cw
            for y in (m * 0.75, H - m * 0.75):
                self.text(x, y - 1.4, str(i + 1), 3.2, anchor="c")
            if i:
                xx = m + i * cw
                self.line(xx, m / 2, xx, m); self.line(xx, H - m, xx, H - m / 2)
        for j in range(vz):
            y = H - m - (j + 0.5) * ch
            for x in (m * 0.75, W - m * 0.75):
                self.text(x, y - 1.4, "ABCDEFGHJKLM"[j], 3.2, anchor="c")
            if j:
                yy = H - m - j * ch
                self.line(m / 2, yy, m, yy); self.line(W - m, yy, W - m / 2, yy)
        # centering marks (triangles + ticks)
        for (x, y, a) in ((W / 2, H - m, -90), (W / 2, m, 90), (m, H / 2, 0), (W - m, H / 2, 180)):
            self.centering(x, y, a)

    def centering(self, x, y, ang):
        a = math.radians(ang); ca, sa = math.cos(a), math.sin(a)
        pts = [(x - 4 * ca, y - 4 * sa)]
        for s in (1, -1):
            pts.append((x - 4 * ca - s * 3 * sa, y - 4 * sa + s * 3 * ca))
        self.poly([pts[1], (x + 0 * ca, y + 0 * sa), pts[2], pts[1]], LW_THIN)
        self.line(x - 6 * ca, y - 6 * sa, x + 4 * ca, y + 4 * sa, LW_THIN)

    # ---- tables -----------------------------------------------------------
    def table(self, x, y_top, col_w, row_h, rows, h=3.2):
        """rows: list of lists of (text, span) or text; bold if text startswith '*'."""
        y = y_top
        total = sum(col_w)
        for r in rows:
            cx = x; ci = 0
            for cell in r:
                t, span = (cell if isinstance(cell, tuple) else (cell, 1))
                w = sum(col_w[ci:ci + span])
                self.rect(cx, y - row_h, w, row_h, LW_THIN)
                bold = t.startswith("*"); t = t.lstrip("*")
                if t:
                    f = "MonoB" if bold else "Mono"
                    hh = min(h, h * (w - 1.5) / max(self.tw(t, h, f), 1e-6))   # rimpicciolisci se non entra
                    self.text(cx + w / 2, y - row_h / 2 - hh * 0.36, t, hh, f, "c")
                cx += w; ci += span
            y -= row_h
        self.rect(x, y, total, y_top - y, LW_FRAME)
        return y

    # ---- views ------------------------------------------------------------
    def view(self, proj, ox, oy, s, label=None, scale_txt=None, label_xy=None):
        """proj: dict from hlr.project; (ox,oy) sheet position of projected origin; s scale."""
        T = lambda p: [(ox + s * a, oy + s * b) for a, b in p]
        for e in proj.get("tangent", []): self.poly(T(e), LW_THIN)
        for e in proj.get("visible", []): self.poly(T(e), LW_VIS)
        for e in proj.get("hidden", []): self.poly(T(e), LW_THIN, dash=(2, 1))
        if label:
            lx, ly = label_xy
            self.text(lx, ly, label, 4.0)
            self.text(lx, ly - 6, f"Scala:  {scale_txt}", 4.0)
        return lambda x, y: (ox + s * x, oy + s * y)

    def centerline(self, p1, p2):
        self.poly([p1, p2], LW_THIN, dash=(8, 1.5, 1, 1.5))

    def center_mark(self, c, r):
        x, y = c; e = r + 2.5
        self.centerline((x - e, y), (x + e, y)); self.centerline((x, y - e), (x, y + e))

    # ---- dimensions (all positions in SHEET mm) ---------------------------
    def dim_text(self, val, tol):
        return val, (f"±{tol}" if tol else "")

    def balloon(self, x, y, n):
        self.lw(LW_THIN); self.c.circle(x * mm, y * mm, 3.2 * mm, stroke=1, fill=0)
        self.text(x, y - 1.25, str(n), 3.2, "MonoB", "c")

    def _label(self, x, y, val, tol, rot=0, anchor="c", balloon=None):
        """Draw value + small tolerance, centred at (x,y) along direction rot (0 or 90)."""
        tsz = TXT * 0.62
        wv, wt = self.tw(val), (self.tw(tol, tsz) + 0.8 if tol else 0)
        tot = wv + wt
        a = math.radians(rot); ca, sa = math.cos(a), math.sin(a)
        start = {"c": -tot / 2, "l": 0, "r": -tot}[anchor]
        px, py = x + start * ca, y + start * sa
        self.text(px, py, val, TXT, rot=rot)
        if tol:
            self.text(px + (wv + 0.8) * ca - 0.0 * sa, py + (wv + 0.8) * sa, tol, tsz, rot=rot)
        if balloon:
            k = -5 if anchor == "r" else tot + 5  # balloon on the far end of the text
            if rot == 0: self.balloon(px + k, py + TXT / 2, balloon)
            elif anchor in ("r", "c"): self.balloon(px - TXT - 4.5, py + tot / 2, balloon)  # beside the text
            else: self.balloon(px - TXT / 2, py + k, balloon)

    def hdim(self, p1, p2, y, val, tol="±0.25", balloon=None, text_side=None):
        (x1, y1), (x2, y2) = p1, p2
        if x1 > x2: (x1, y1), (x2, y2) = (x2, y2), (x1, y1)
        for (x, yy) in ((x1, y1), (x2, y2)):
            d = 1 if y > yy else -1
            self.line(x, yy + d * 1.0, x, y + d * 2.0)
        L = x2 - x1
        need = self.tw(val) + 8
        self.line(x1, y, x2, y)
        if L > need:
            self.arrow(x1, y, math.pi); self.arrow(x2, y, 0)
            self._label((x1 + x2) / 2, y + 1.0, val, tol, 0, "c", balloon)
        else:  # arrows outside, text to the right (or left)
            self.line(x1 - 6, y, x1, y); self.line(x2, y, x2 + 6, y)
            self.arrow(x1, y, 0); self.arrow(x2, y, math.pi)
            if text_side == "l":
                self._label(x1 - 7, y + 1.0, val, tol, 0, "r", balloon)
            else:
                self._label(x2 + 7, y + 1.0, val, tol, 0, "l", balloon)

    def vdim(self, p1, p2, x, val, tol="±0.25", balloon=None, text_side=None):
        (x1, y1), (x2, y2) = p1, p2
        if y1 > y2: (x1, y1), (x2, y2) = (x2, y2), (x1, y1)
        for (xx, yy) in ((x1, y1), (x2, y2)):
            d = 1 if x > xx else -1
            self.line(xx + d * 1.0, yy, x + d * 2.0, yy)
        L = y2 - y1
        need = self.tw(val) + 8
        self.line(x, y1, x, y2)
        if L > need:
            self.arrow(x, y1, -math.pi / 2); self.arrow(x, y2, math.pi / 2)
            self._label(x - 1.0, (y1 + y2) / 2, val, tol, 90, "c", balloon)
        else:
            self.line(x, y1 - 6, x, y1); self.line(x, y2, x, y2 + 6)
            self.arrow(x, y1, math.pi / 2); self.arrow(x, y2, -math.pi / 2)
            if text_side == "d":
                self._label(x - 1.0, y1 - 7, val, tol, 90, "r", balloon)
            else:
                self._label(x - 1.0, y2 + 7, val, tol, 90, "l", balloon)

    def leader(self, p_on, p_knee, text, tol="", balloon=None, right=True):
        """Leader with arrow on p_on, knee then horizontal shoulder with text."""
        (x0, y0), (xk, yk) = p_on, p_knee
        self.line(x0, y0, xk, yk)
        self.arrow(x0, y0, math.atan2(y0 - yk, x0 - xk))
        tsz = TXT * 0.62
        w = self.tw(text) + (self.tw(tol, tsz) + 0.8 if tol else 0) + 2
        xe = xk + (w if right else -w)
        self.line(xk, yk, xe, yk)
        if right:
            self._label(xk + 1, yk + 1.0, text, tol, 0, "l", balloon)
        else:  # testo che finisce sul gomito, pallino all'estremita' esterna (sinistra)
            self._label(xk - 1, yk + 1.0, text, tol, 0, "r", balloon)

    def save(self): self.c.showPage(); self.c.save()


def projection_symbol(sh, x, y, first_angle=True, k=1.0):
    """ISO projection method symbol (first angle by default), centred at (x,y)."""
    r1, r2 = 2.5 * k, 5 * k
    cx = x + (6 * k if first_angle else -6 * k)
    sh.lw(LW_THIN)
    sh.c.circle(cx * mm, y * mm, r1 * mm); sh.c.circle(cx * mm, y * mm, r2 * mm)
    tx = x - 6 * k if first_angle else x + 6 * k
    L = 9 * k
    xa, xb = (tx - L / 2, tx + L / 2)
    pts = [(xa, y - r1), (xb, y - r2), (xb, y + r2), (xa, y + r1), (xa, y - r1)] if first_angle else \
          [(xa, y - r2), (xb, y - r1), (xb, y + r1), (xa, y + r2), (xa, y - r2)]
    sh.poly(pts, LW_THIN)
    sh.centerline((tx - L / 2 - 2, y), (cx + r2 + 2, y))
