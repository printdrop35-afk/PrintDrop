"""PrintDrop pour Windows — fenêtre principale (Tk, sans dépendance supplémentaire).

Une seule instance : la 2e ouverture (raccourci, démarrage Windows) affiche la fenêtre déjà lancée.
Fermer la fenêtre la masque : l'agent continue d'imprimer en arrière-plan. « Quitter » l'arrête.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.parse import urlparse

import printdrop_agent as core

NAVY, BLUE, BLUE_D, SKY = "#09265C", "#2563EB", "#1D4ED8", "#EEF4FF"
INK, MUTED, LINE, BG, WHITE = "#0F172A", "#64748B", "#E2E8F0", "#F5F8FC", "#FFFFFF"
OK, WARN, ERR = "#059669", "#B45309", "#DC2626"
FONT = "Segoe UI" if core.IS_WINDOWS else "DejaVu Sans"
MONO = "Consolas" if core.IS_WINDOWS else "DejaVu Sans Mono"
LOCK_PORT = 47813
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_DIR = Path(__file__).resolve().parent
CONN = {"usb": "USB", "wifi": "Wi-Fi", "ethernet": "Ethernet", "network": "Réseau", "virtual": "Virtuelle", "unknown": "—"}


# ---------------------------------------------------------------- single instance
def acquire_single_instance(on_show) -> socket.socket | None:
    """Returns the lock socket, or None if PrintDrop already runs (it is then asked to show its window)."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        srv.bind(("127.0.0.1", LOCK_PORT))
    except OSError:
        try:
            with socket.create_connection(("127.0.0.1", LOCK_PORT), timeout=2) as c:
                c.sendall(b"SHOW")
        except OSError:
            pass
        return None
    srv.listen(2)

    def serve():
        while True:
            try:
                conn, _ = srv.accept()
                with conn:
                    if conn.recv(16).startswith(b"SHOW"):
                        on_show()
            except OSError:
                return
    threading.Thread(target=serve, daemon=True).start()
    return srv


# ---------------------------------------------------------------- Windows autostart (user choice)
def autostart_enabled() -> bool | None:
    if not core.IS_WINDOWS:
        return None
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, "PrintDrop")
            return True
    except OSError:
        return False


def set_autostart(on: bool) -> None:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            exe = Path(sys.executable).with_name("pythonw.exe")
            winreg.SetValueEx(k, "PrintDrop", 0, winreg.REG_SZ, f'"{exe}" "{APP_DIR / "printdrop_agent.py"}" --background')
        else:
            try:
                winreg.DeleteValue(k, "PrintDrop")
            except OSError:
                pass


def open_path(target: str) -> None:
    if core.IS_WINDOWS:
        os.startfile(target)  # noqa: S606 - local file / ms-settings URI chosen by the app
    else:
        webbrowser.open(target)


# ---------------------------------------------------------------- widgets
def button(parent, text, cmd, kind="primary", **kw) -> tk.Button:
    colors = {"primary": (BLUE, WHITE, BLUE_D), "ghost": (WHITE, INK, SKY), "danger": (WHITE, ERR, "#FEF2F2")}[kind]
    b = tk.Button(parent, text=text, command=cmd, bg=colors[0], fg=colors[1], activebackground=colors[2], activeforeground=colors[1],
                  relief="flat", bd=0, cursor="hand2", font=(FONT, 10, "bold" if kind == "primary" else "normal"), padx=10, pady=6,
                  highlightthickness=1 if kind != "primary" else 0, highlightbackground=LINE, **kw)
    b.bind("<Enter>", lambda e: b.config(bg=colors[2]))
    b.bind("<Leave>", lambda e: b.config(bg=colors[0]))
    return b


def card(parent, title: str | None = None) -> tuple[tk.Frame, tk.Frame]:
    outer = tk.Frame(parent, bg=WHITE, highlightthickness=1, highlightbackground=LINE, highlightcolor=LINE)
    if title:
        tk.Label(outer, text=title.upper(), bg=WHITE, fg=MUTED, font=(FONT, 8, "bold")).pack(anchor="w", padx=16, pady=(12, 0))
    inner = tk.Frame(outer, bg=WHITE)
    inner.pack(fill="both", expand=True, padx=16, pady=(6, 14))
    return outer, inner


class App:
    def __init__(self, background: bool):
        self.root = tk.Tk()
        self.root.title(f"PrintDrop pour Windows — v{core.VERSION}")
        self.root.geometry("1040x720")
        self.root.minsize(860, 600)
        self.root.configure(bg=BG)
        self.agent: core.Agent | None = None
        self.logo = self._load_logo()
        if self.logo is not None:
            try:
                self.root.iconphoto(True, self.logo)
            except tk.TclError:
                pass
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("PD.Treeview", font=(FONT, 10), rowheight=28, background=WHITE, fieldbackground=WHITE, bordercolor=LINE, borderwidth=0)
        style.configure("PD.Treeview.Heading", font=(FONT, 9, "bold"), background=SKY, foreground=NAVY, relief="flat", padding=(6, 6))
        style.map("PD.Treeview", background=[("selected", "#DBE7FF")], foreground=[("selected", INK)])
        self._header()
        self.body = tk.Frame(self.root, bg=BG)
        self.body.pack(fill="both", expand=True, padx=20, pady=14)
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        cfg = core.load_json(core.CONFIG_FILE, None)
        if cfg:
            self.start(cfg)
            if background:
                self.root.withdraw()  # started with Windows: works silently, window on demand
        else:
            self.pair_view()

    # ---- chrome
    def _load_logo(self, size: int = 34):
        src = APP_DIR / "printdrop-logo.png"
        if not src.exists():
            return None
        try:
            from PIL import Image, ImageTk
            return ImageTk.PhotoImage(Image.open(src).convert("RGBA").resize((size, size)))
        except Exception:
            return None

    def _header(self):
        h = tk.Frame(self.root, bg=NAVY, height=64)
        h.pack(fill="x")
        h.pack_propagate(False)
        if self.logo is not None:
            tk.Label(h, image=self.logo, bg=NAVY).pack(side="left", padx=(20, 10))
        txt = tk.Frame(h, bg=NAVY)
        txt.pack(side="left", padx=(0 if self.logo else 20, 0))
        tk.Label(txt, text="PrintDrop", bg=NAVY, fg=WHITE, font=(FONT, 15, "bold")).pack(anchor="w", pady=(10, 0))
        tk.Label(txt, text=f"Agent Windows · v{core.VERSION}", bg=NAVY, fg="#A9C1F5", font=(FONT, 9)).pack(anchor="w")
        self.pill = tk.Label(h, text="", bg=NAVY, fg=WHITE, font=(FONT, 10, "bold"), padx=12, pady=5)
        self.pill.pack(side="right", padx=20)

    def set_pill(self, text: str, color: str):
        self.pill.config(text=f"●  {text}", bg=color)

    def clear(self):
        for w in self.body.winfo_children():
            w.destroy()

    def show(self):
        self.root.after(0, lambda: (self.root.deiconify(), self.root.lift(), self.root.focus_force()))

    def hide(self):
        if self.agent and not self.agent.revoked:
            self.root.withdraw()  # keeps printing in the background
        else:
            self.root.destroy()

    def quit(self):
        if messagebox.askyesno("Quitter PrintDrop", "Les commandes ne seront plus imprimées sur ce PC tant que PrintDrop est fermé.\n\nQuitter quand même ?"):
            if self.agent:
                self.agent.stop.set()
            self.root.destroy()

    # ---- pairing
    def pair_view(self, error: str = ""):
        self.clear()
        self.set_pill("Non associé", WARN)
        wrap = tk.Frame(self.body, bg=BG)
        wrap.place(relx=0.5, rely=0.45, anchor="center")
        outer, c = card(wrap)
        outer.pack(ipadx=10)
        tk.Label(c, text="Associez ce PC à votre boutique", bg=WHITE, fg=INK, font=(FONT, 17, "bold")).pack(anchor="w", pady=(6, 2))
        tk.Label(c, text="Une seule fois : ensuite PrintDrop imprime les commandes automatiquement.", bg=WHITE, fg=MUTED, font=(FONT, 10)).pack(anchor="w")
        steps = tk.Frame(c, bg=WHITE)
        steps.pack(fill="x", pady=16)
        for i, t in enumerate(["Sur printdrop.fr, ouvrez « Imprimantes et périphériques »",
                               "Cliquez sur « Générer un code d'appairage »", "Saisissez le code ci-dessous"], 1):
            row = tk.Frame(steps, bg=WHITE)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=str(i), bg=SKY, fg=BLUE, font=(FONT, 10, "bold"), width=3).pack(side="left")
            tk.Label(row, text=t, bg=WHITE, fg=INK, font=(FONT, 10)).pack(side="left", padx=10)
        code = tk.StringVar()
        code.trace_add("write", lambda *_: code.set(code.get().upper().replace(" ", "")[:12]) if code.get() != code.get().upper().replace(" ", "")[:12] else None)
        e = tk.Entry(c, textvariable=code, font=(MONO, 22, "bold"), justify="center", width=14, relief="flat", bg=SKY, fg=NAVY,
                     highlightthickness=2, highlightbackground=LINE, highlightcolor=BLUE, insertbackground=NAVY)
        e.pack(fill="x", ipady=8)
        e.focus_set()
        server = tk.StringVar(value=core.DEFAULT_SERVER)
        adv = tk.Frame(c, bg=WHITE)
        msg = tk.Label(c, text=error, bg=WHITE, fg=ERR, font=(FONT, 10), wraplength=440, justify="left")
        msg.pack(anchor="w", pady=(10, 0))
        go = button(c, "Associer ce PC", lambda: self._do_pair(server.get(), code.get(), go, msg))
        go.pack(fill="x", pady=(10, 4))
        e.bind("<Return>", lambda _e: go.invoke())

        def toggle():
            if adv.winfo_ismapped():
                adv.pack_forget()
            else:
                adv.pack(fill="x", pady=(6, 0))
        tk.Button(c, text="Paramètres avancés", command=toggle, bg=WHITE, fg=MUTED, relief="flat", bd=0, cursor="hand2",
                  font=(FONT, 9, "underline"), activebackground=WHITE, highlightthickness=0).pack(anchor="w")
        tk.Label(adv, text="Adresse du serveur PrintDrop", bg=WHITE, fg=MUTED, font=(FONT, 9)).pack(anchor="w")
        tk.Entry(adv, textvariable=server, font=(FONT, 10), relief="flat", bg=SKY).pack(fill="x", ipady=4)

    def _do_pair(self, server: str, code: str, btn: tk.Button, msg: tk.Label):
        btn.config(state="disabled", text="Association en cours…")
        msg.config(text="", fg=ERR)

        def work():
            try:
                shop = core.pair(server, code, socket.gethostname())
                self.root.after(0, lambda: self.start(core.load_json(core.CONFIG_FILE, {}), shop))
            except SystemExit as exc:
                err = str(exc)
                self.root.after(0, lambda: (msg.config(text=err), btn.config(state="normal", text="Associer ce PC")))
        threading.Thread(target=work, daemon=True).start()

    # ---- dashboard
    def start(self, cfg: dict, shop: str | None = None):
        try:
            self.agent = core.start_agent()
        except SystemExit as exc:
            return self.pair_view(str(exc))
        self.cfg = cfg
        self.dashboard()
        self.tick()

    def dashboard(self):
        self.clear()
        b = self.body
        self.banner = tk.Frame(b, bg="#FFF7ED", highlightthickness=1, highlightbackground="#FED7AA")
        self.banner_text = tk.Label(self.banner, bg="#FFF7ED", fg=WARN, font=(FONT, 10, "bold"), wraplength=760, justify="left")
        self.banner_text.pack(side="left", padx=14, pady=10)
        self.banner_btn = button(self.banner, "Associer de nouveau", self.unpair, kind="ghost")
        foot = tk.Frame(b, bg=BG)
        foot.pack(side="bottom", fill="x", pady=(10, 0))
        auto = autostart_enabled()
        self.v_auto = tk.BooleanVar(value=bool(auto))
        cb = tk.Checkbutton(foot, text="Démarrer PrintDrop avec Windows", variable=self.v_auto, command=self.toggle_autostart, bg=BG, fg=INK,
                            activebackground=BG, font=(FONT, 10), state="normal" if auto is not None else "disabled", selectcolor=WHITE)
        cb.pack(side="left")
        tk.Label(foot, text="· Fermer la fenêtre laisse PrintDrop actif", bg=BG, fg=MUTED, font=(FONT, 8)).pack(side="left", padx=4)
        button(foot, "Quitter", self.quit, kind="danger").pack(side="right")
        button(foot, "Dissocier ce PC", self.confirm_unpair, kind="ghost").pack(side="right", padx=6)
        button(foot, "Journal", lambda: open_path(str(core.LOG_FILE)), kind="ghost").pack(side="right")
        button(foot, "Ouvrir PrintDrop", lambda: webbrowser.open(self._url("/dashboard")), kind="ghost").pack(side="right", padx=6)

        top = tk.Frame(b, bg=BG)
        top.pack(fill="x")
        self.v_conn, self.v_sync, self.v_shop, self.v_srv = (tk.StringVar() for _ in range(4))
        for i, (title, big, small) in enumerate([("Connexion", self.v_conn, self.v_sync), ("Boutique associée", self.v_shop, self.v_srv),
                                                 ("Ce PC", tk.StringVar(value=socket.gethostname()[:22]), tk.StringVar(value=f"Agent v{core.VERSION} · Windows"))]):
            o, c = card(top, title)
            o.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 12, 0))
            top.columnconfigure(i, weight=1, uniform="cards")
            lbl = tk.Label(c, textvariable=big, bg=WHITE, fg=INK, font=(FONT, 13, "bold"), anchor="w")
            lbl.pack(fill="x")
            if i == 0:
                self.conn_label = lbl
            tk.Label(c, textvariable=small, bg=WHITE, fg=MUTED, font=(FONT, 9), anchor="w").pack(fill="x")
        mid = tk.Frame(b, bg=BG)
        mid.pack(fill="both", expand=True, pady=14)
        mid.columnconfigure(0, weight=3)
        mid.columnconfigure(1, weight=2)
        mid.rowconfigure(0, weight=1)
        po, pc = card(mid, "Imprimantes détectées sur ce PC")
        po.grid(row=0, column=0, sticky="nsew")
        self.t_printers = self._tree(pc, [("name", "Imprimante", 260), ("conn", "Connexion", 90), ("state", "État", 170)], 5)
        bar = tk.Frame(pc, bg=WHITE)
        bar.pack(fill="x", pady=(8, 0))
        button(bar, "Imprimer une page de test", self.test_page).pack(side="left")
        button(bar, "Ajouter une imprimante", lambda: webbrowser.open(self._url("/dashboard/imprimantes")), kind="ghost").pack(side="left", padx=6)
        button(bar, "Paramètres Windows", lambda: open_path("ms-settings:printers"), kind="ghost").pack(side="left")
        so, sc = card(mid, "Scanners")
        so.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        self.t_scanners = self._tree(sc, [("name", "Scanner", 170), ("glass", "Vitre", 48), ("feed", "ADF", 44), ("dup", "R°/V°", 52)], 5)
        tk.Label(sc, text="Les scans se lancent depuis le Comptoir de printdrop.fr.", bg=WHITE, fg=MUTED, font=(FONT, 9), wraplength=300,
                 justify="left").pack(anchor="w", pady=(8, 0))
        jo, jc = card(b, "Activité récente")
        jo.pack(fill="both", expand=True)
        self.t_jobs = self._tree(jc, [("at", "Heure", 60), ("kind", "Type", 200), ("detail", "Détail", 490), ("res", "Résultat", 90)], 4)
    def _tree(self, parent, cols, height) -> ttk.Treeview:
        t = ttk.Treeview(parent, columns=[c[0] for c in cols], show="headings", height=height, style="PD.Treeview", selectmode="browse")
        for key, title, width in cols:
            t.heading(key, text=title, anchor="w")
            t.column(key, width=width, anchor="w", stretch=key in ("name", "detail"))
        t.tag_configure("ok", foreground=OK)
        t.tag_configure("bad", foreground=ERR)
        t.tag_configure("muted", foreground=MUTED)
        t.pack(fill="both", expand=True)
        return t

    def _url(self, path: str) -> str:
        return self.cfg.get("server", core.DEFAULT_SERVER).rstrip("/") + path

    def _fill(self, tree: ttk.Treeview, rows: list[tuple], empty: str, empty_col: int = 0):
        sel = tree.selection()
        tree.delete(*tree.get_children())
        if not rows:
            tree.insert("", "end", values=tuple([""] * empty_col + [empty]), tags=("muted",))
        for iid, values, tag in rows:
            tree.insert("", "end", iid=iid, values=values, tags=(tag,))
        if sel and tree.exists(sel[0]):
            tree.selection_set(sel[0])

    def tick(self):
        a = self.agent
        if not a or not self.root.winfo_exists():
            return
        if a.revoked:
            self.set_pill("Dissocié", ERR)
            self.v_conn.set("Dissocié")
            self.conn_label.config(fg=ERR)
        elif a.connected:
            self.set_pill("En ligne", OK)
            self.v_conn.set("En ligne")
            self.conn_label.config(fg=OK)
        else:
            self.set_pill("Reconnexion…" if a.last_ok else "Connexion…", WARN)
            self.v_conn.set("Hors ligne" if a.last_ok else "Connexion…")
            self.conn_label.config(fg=WARN)
        self.v_sync.set(f"Synchronisé à {time.strftime('%H:%M:%S', time.localtime(a.last_ok))}" if a.last_ok else "En attente du serveur…")
        self.v_shop.set(self.cfg.get("shop") or "—")
        self.v_srv.set(urlparse(self.cfg.get("server", "")).netloc)
        if a.error:
            self.banner_text.config(text=a.error)
            if not self.banner.winfo_ismapped():
                self.banner.pack(fill="x", pady=(0, 12), before=self.body.winfo_children()[1])
            if a.revoked and not self.banner_btn.winfo_ismapped():
                self.banner_btn.pack(side="right", padx=10)
        elif self.banner.winfo_ismapped():
            self.banner.pack_forget()
        self._fill(self.t_printers, [(p["name"], (("★ " if p.get("is_default") else "") + p["name"], CONN.get(p.get("connection_type"), "—"),
                                                  "Prête" if p["status"] == "online" else (p.get("detail") or ("En erreur" if p["status"] == "error" else "Hors ligne"))),
                                      "ok" if p["status"] == "online" else "bad") for p in a.printers],
                   "Aucune imprimante installée dans Windows — cliquez sur « Ajouter une imprimante »")
        yes = lambda v: "✓" if v else "—"  # noqa: E731
        self._fill(self.t_scanners, [(f"s{i}", (s["name"], yes(s.get("flatbed")), yes(s.get("feeder")), yes(s.get("duplex"))), "")
                                     for i, s in enumerate(a.scanners)], "Aucun scanner détecté")
        self._fill(self.t_jobs, [(f"j{i}", (time.strftime("%H:%M", time.localtime(j["at"])), j["kind"], j["detail"], "✓ Réussi" if j["ok"] else "✗ Échec"),
                                  "ok" if j["ok"] else "bad") for i, j in enumerate(list(a.activity)[:30])], "Aucune activité depuis le démarrage", empty_col=2)
        self.root.after(1500, self.tick)

    # ---- actions
    def test_page(self):
        sel = self.t_printers.selection()
        if not sel or not self.agent or sel[0] not in {p["name"] for p in self.agent.printers}:
            messagebox.showinfo("PrintDrop", "Sélectionnez d'abord une imprimante dans la liste.")
            return
        name, a = sel[0], self.agent

        def work():
            try:
                res = a.backend.test_page({"printer_name": name})
                a.note("Page de test", f"{name} : {res.get('note') or 'envoyée'}", bool(res.get("submitted", True)))
            except Exception as exc:  # noqa: BLE001 - shown to the employee
                a.note("Page de test", f"{name} : {exc}", False)
        threading.Thread(target=work, daemon=True).start()

    def toggle_autostart(self):
        try:
            set_autostart(self.v_auto.get())
        except OSError as exc:
            messagebox.showerror("PrintDrop", f"Impossible de modifier le démarrage automatique : {exc}")
            self.v_auto.set(not self.v_auto.get())

    def confirm_unpair(self):
        if messagebox.askyesno("Dissocier ce PC", "Ce PC ne recevra plus les commandes de la boutique.\nVous pourrez l'associer de nouveau avec un nouveau code.\n\nDissocier ?"):
            self.unpair()

    def unpair(self):
        if self.agent:
            self.agent.stop.set()
            self.agent = None
        core.CONFIG_FILE.unlink(missing_ok=True)
        self.pair_view()

    def run(self):
        self.root.mainloop()


def run_app(background: bool = False) -> None:
    holder: dict = {}
    lock = acquire_single_instance(lambda: holder["app"].show() if "app" in holder else None)
    if lock is None:
        return  # already running: its window was brought to the front
    holder["app"] = App(background)
    holder["app"].run()
