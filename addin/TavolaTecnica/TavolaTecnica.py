"""Add-in Fusion 360: pulsante "Genera tavola" (scheda SOLIDO) che crea la tavola tecnica A3
del design attivo. I dati del cartiglio restano salvati nel design (attributi), nessun file
nella cartella del progetto oltre al PDF."""
import json, os, re, subprocess, traceback
import adsk.core, adsk.fusion
from . import core

CMD_ID = "TavolaTecnica_Genera"
PANEL_ID = "TavolaTecnica_Panel"
EVENTO = "TavolaTecnica_Fine"
STANDARD = "Standard"
CAMPI = [("intestazione", "Intestazione"), ("autore", "Disegnato da"), ("titolo", "Titolo"), ("numero", "N. disegno"), ("materiale", "Materiale"),
         ("densita", "Densità (g/cm³)"), ("fabbricazione", "Fabbricazione"), ("nota", "Nota")]

app = adsk.core.Application.get()
ui = app.userInterface
handlers = []
stato = {}       # documento e config del comando in corso
da_pulire = {}   # nome documento -> vecchio tavola.json importato, da cancellare quando il design viene salvato


def _errore(titolo):
    ui.messageBox(f"{titolo}\n\n{traceback.format_exc()}", "Tavola tecnica")


def _val(inputs, k):
    return inputs.itemById(k).value.strip()


def _cfg_da_dialogo(inputs):
    cfg = dict(stato["cfg"])
    for k, _ in CAMPI + [("rev", ""), ("descrizione", ""), ("cartella", ""), ("nome_file", "")]:
        cfg[k] = _val(inputs, k)
    cfg["densita"] = float(cfg["densita"].replace(",", "."))
    r = inputs.itemById("ricetta").selectedItem.name
    cfg["ricetta"] = "" if r == STANDARD else r
    return cfg


def _breve(p):
    h = os.path.expanduser("~")
    return "~" + p[len(h):] if p.startswith(h) else p


def _anteprima(inputs):
    try:
        cfg = _cfg_da_dialogo(inputs)
        t = core.percorso_pdf(cfg) if cfg["cartella"] else "(scegli la cartella del progetto)"
    except ValueError:
        t = "(densità non valida)"
    inputs.itemById("pdf").text = _breve(t)


class CreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            if not adsk.fusion.Design.cast(app.activeProduct):
                ui.messageBox("Porta in primo piano il design 3D del pezzo, poi riprova.", "Tavola tecnica")
                return
            doc = app.activeDocument
            cfg, origine = core.leggi_config(doc)
            stato.update(doc=doc, cfg=cfg, origine=origine,
                         prima=json.dumps(cfg, sort_keys=True) if origine == "documento" else "")

            cmd = args.command
            cmd.okButtonText = "Genera"
            cmd.setDialogInitialSize(480, 700)
            cmd.setDialogMinimumSize(420, 400)
            inputs = cmd.commandInputs
            if origine and origine != "documento":
                inputs.addTextBoxCommandInput("info", "", "Dati importati da " + _breve(origine)
                                              + ". Da ora restano salvati nel design.", 2, True)
            g = inputs.addGroupCommandInput("g_cartiglio", "Cartiglio").children
            for k, label in CAMPI:
                g.addStringValueInput(k, label, str(cfg[k]))
            dd = g.addDropDownCommandInput("ricetta", "Tipo tavola", adsk.core.DropDownStyles.TextListDropDownStyle)
            for r in [STANDARD] + core.ricette():
                dd.listItems.add(r, r == (cfg["ricetta"] or STANDARD), "")
            if not dd.selectedItem:
                dd.listItems.item(0).isSelected = True

            g = inputs.addGroupCommandInput("g_rev", "Emissione").children
            g.addStringValueInput("rev", "Revisione", cfg["rev"])
            g.addStringValueInput("descrizione", "Descrizione", cfg["descrizione"])

            g = inputs.addGroupCommandInput("g_out", "Uscita").children
            g.addStringValueInput("cartella", "Cartella progetto", cfg["cartella"])
            g.addBoolValueInput("sfoglia", "Sfoglia", False, "", False).text = "Scegli cartella…"
            g.addStringValueInput("nome_file", "Nome file", cfg["nome_file"])
            g.addTextBoxCommandInput("pdf", "PDF", "", 2, True)
            _anteprima(inputs)

            for ev, h in ((cmd.execute, ExecuteHandler()), (cmd.inputChanged, ChangedHandler()),
                          (cmd.validateInputs, ValidateHandler())):
                ev.add(h); handlers.append(h)
        except Exception:
            _errore("Errore nell'apertura del comando")


class ChangedHandler(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        try:
            inputs = args.firingEvent.sender.commandInputs   # args.inputs = solo il gruppo modificato
            if args.input.id == "sfoglia":
                dlg = ui.createFolderDialog()
                dlg.title = "Cartella del progetto"
                cur = inputs.itemById("cartella").value.strip()
                dlg.initialDirectory = cur if os.path.isdir(cur) else core.PROGETTI
                if dlg.showDialog() == adsk.core.DialogResults.DialogOK:
                    inputs.itemById("cartella").value = dlg.folder
            _anteprima(inputs)
        except Exception:
            _errore("Errore")


class ValidateHandler(adsk.core.ValidateInputsEventHandler):
    def notify(self, args):
        i = args.inputs
        try:
            float(_val(i, "densita").replace(",", "."))
            ok = True
        except ValueError:
            ok = False
        args.areInputsValid = ok and os.path.isdir(_val(i, "cartella")) and all(
            _val(i, k) for k in ("rev", "nome_file", "titolo", "numero"))


class ExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            doc = stato["doc"]
            cfg = _cfg_da_dialogo(args.command.commandInputs)
            core.salva_config(doc, cfg)
            if stato["origine"] and stato["origine"] != "documento":
                da_pulire[doc.name] = stato["origine"]
            cambiata = json.dumps(cfg, sort_keys=True) != stato["prima"]
            out = core.percorso_pdf(cfg)
            step = os.path.join(core.nuova_cartella_temp(), re.sub(r"[^\w.-]+", "_", cfg["nome_file"]) + ".step")
            P, G = core.leggi_dati(doc, cfg, step)

            def fine(ok, out, log):
                app.fireCustomEvent(EVENTO, json.dumps({"ok": ok, "out": out, "log": log[-3000:], "salva": cambiata}))
            core.avvia(dict(cfg, documento=doc.name), P, G, step, out, fine)
            core.notifica("Calcolo viste e disegno in corso…", "Tavola " + cfg["nome_file"])
        except Exception:
            _errore("Generazione non riuscita")


class FineHandler(adsk.core.CustomEventHandler):
    def notify(self, args):
        try:
            r = json.loads(args.additionalInfo)
            if r["ok"]:
                subprocess.Popen(["open", r["out"]])
                msg = "Tavola pronta: " + os.path.basename(r["out"])
                if r["salva"]:
                    msg += " — salva il design per conservare i dati del cartiglio"
                core.notifica(msg)
            else:
                ui.messageBox("Generazione della tavola non riuscita.\n\n" + r["log"], "Tavola tecnica")
        except Exception:
            _errore("Errore")


class SalvatoHandler(adsk.core.DocumentEventHandler):
    """Dopo il salvataggio i dati sono nel design: il vecchio tavola.json (e il .command) non servono piu'."""
    def notify(self, args):
        try:
            p = da_pulire.pop(args.document.name, None)
            if p:
                for f in (p, os.path.join(os.path.dirname(p), "Genera_tavola.command")):
                    if os.path.exists(f):
                        os.remove(f)
        except Exception:
            _errore("Pulizia del vecchio tavola.json non riuscita")


def run(context):
    try:
        h = SalvatoHandler(); app.documentSaved.add(h); handlers.append(h)
        ev = app.registerCustomEvent(EVENTO)
        h = FineHandler(); ev.add(h); handlers.append(h)

        cd = ui.commandDefinitions.itemById(CMD_ID)
        if cd:
            cd.deleteMe()
        cd = ui.commandDefinitions.addButtonDefinition(
            CMD_ID, "Genera tavola", "Crea la tavola tecnica A3 (PDF) del design attivo.\n"
            "I dati del cartiglio restano salvati nel design.", os.path.join(os.path.dirname(__file__), "resources"))
        h = CreatedHandler(); cd.commandCreated.add(h); handlers.append(h)

        tab = ui.workspaces.itemById("FusionSolidEnvironment").toolbarTabs.itemById("SolidTab")
        panel = tab.toolbarPanels.itemById(PANEL_ID) or tab.toolbarPanels.add(PANEL_ID, "TAVOLA")
        ctl = panel.controls.itemById(CMD_ID) or panel.controls.addCommand(cd)
        ctl.isPromoted = ctl.isPromotedByDefault = True
    except Exception:
        _errore("Avvio dell'add-in TavolaTecnica non riuscito")


def stop(context):
    try:
        tab = ui.workspaces.itemById("FusionSolidEnvironment").toolbarTabs.itemById("SolidTab")
        panel = tab.toolbarPanels.itemById(PANEL_ID)
        if panel:
            panel.deleteMe()
        cd = ui.commandDefinitions.itemById(CMD_ID)
        if cd:
            cd.deleteMe()
        app.unregisterCustomEvent(EVENTO)
        handlers.clear()
    except Exception:
        _errore("Arresto dell'add-in TavolaTecnica non riuscito")
