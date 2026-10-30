"""Example recipe: the standard sheet plus a highlighted note under the views.

A recipe is a Python file in ricette/ that defines:
    QUERY    (optional) code run inside Fusion to collect extra geometry into `extra`;
             without it the standard QUERY of generico.py is used
    VISTE    views to project: {key: (view_dir, x_dir)} or a function P -> dict
    disegna  disegna(sh, P, G, PJ, meta, cfg) draws the sheet
             P = user parameters, G = QUERY results, PJ = projected views,
             meta = rev/descrizione/data, cfg = values from the dialog
Pick it in the "Tipo tavola" drop-down of the Genera tavola dialog.
"""
from generico import VISTE, disegna as disegna_standard


def disegna(sh, P, G, PJ, meta, cfg):
    disegna_standard(sh, P, G, PJ, meta, cfg)
    if cfg.get("nota"):
        sh.text(sh.m + 10, sh.m + 6, "NOTA: " + cfg["nota"].upper(), 3.0, "MonoB")
