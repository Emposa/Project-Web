from __future__ import annotations

import copy
import json
import os
import queue
import sys
import threading
import tkinter as tk
import webbrowser
from dataclasses import asdict
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .core import (FIELDS, Catalog, Product, Settings, Store, ValidationError, calculate_prices, database,
                   export_products, make_products, mark_duplicates, now, parse_images,
                   read_table, sheet_names, suggest_mapping, validate_product)
from .research import (ApiFatal, BrowserResearch, Cancelled, Fetcher, OpenAIResearch, ResearchCache,
                       direct_research, domain_list, public_url)
from .secrets import protect


BG, PANEL, INK, MUTED, ACCENT = "#f3f5f8", "#ffffff", "#182437", "#617187", "#087f8c"
GLASS, GLASS_EDGE, GLASS_HOVER, ORANGE_SOFT = "#ffffff", "#dbe2eb", "#d9e2ec", "#087f8c"


def data_folder():
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    path = base / "data"
    try:
        path.mkdir(exist_ok=True)
        probe = path / ".write-probe"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return path
    except OSError:
        path = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ePointCSV"
        path.mkdir(parents=True, exist_ok=True)
        return path


def scroll_text(parent, height=8):
    frame = ttk.Frame(parent)
    text = tk.Text(frame, height=height, wrap="word", font=("Segoe UI", 10), relief="flat", bd=1,
                   bg="#ffffff", fg=INK, insertbackground=ACCENT, selectbackground="#d4ebef",
                   highlightthickness=1, highlightbackground=GLASS_EDGE, padx=10, pady=8, undo=True)
    scrollbar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=scrollbar.set)
    text.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")
    frame.pack(fill="both", expand=True, pady=(4, 8))
    return text


class ImportDialog(tk.Toplevel):
    def __init__(self, app, path):
        super().__init__(app)
        self.app, self.path = app, path
        self.title("Učitavanje i mapiranje stupaca")
        self.geometry("1060x760")
        self.minsize(850, 620)
        self.transient(app)
        self.grab_set()
        self.headers, self.data = [], []
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=Path(path).name, style="Heading.TLabel").pack(anchor="w")
        bar = ttk.Frame(frame)
        bar.pack(fill="x", pady=12)
        self.sheet = tk.StringVar(value=sheet_names(path)[0])
        self.header = tk.StringVar(value="1")
        ttk.Label(bar, text="List").pack(side="left")
        ttk.Combobox(bar, textvariable=self.sheet, values=sheet_names(path), state="readonly", width=30).pack(side="left", padx=8)
        ttk.Label(bar, text="Redak zaglavlja").pack(side="left", padx=(18, 6))
        ttk.Spinbox(bar, from_=1, to=1000, textvariable=self.header, width=5).pack(side="left")
        ttk.Button(bar, text="Očitaj stupce", command=self.read).pack(side="left", padx=12)
        profiles = app.store.get_setting("profiles", {})
        self.profiles = profiles
        self.profile = tk.StringVar()
        profile_bar = ttk.Frame(frame)
        profile_bar.pack(fill="x", pady=(0, 10))
        ttk.Label(profile_bar, text="Profil dobavljača").pack(side="left")
        ttk.Combobox(profile_bar, textvariable=self.profile, values=list(profiles), width=28).pack(side="left", padx=8)
        ttk.Button(profile_bar, text="Primijeni profil", command=self.apply_profile).pack(side="left")
        ttk.Label(profile_bar, text="Upišite naziv profila za spremanje mapiranja.", style="Muted.TLabel").pack(side="left", padx=12)
        mapping = ttk.Frame(frame)
        mapping.pack(fill="x")
        self.vars, self.combos = {}, {}
        for i, (key, label) in enumerate(FIELDS.items()):
            col, row = (i // 6) * 2, i % 6
            ttk.Label(mapping, text=label).grid(row=row, column=col, sticky="w", padx=(0, 12), pady=5)
            var = tk.StringVar()
            combo = ttk.Combobox(mapping, textvariable=var, state="readonly", width=30)
            combo.grid(row=row, column=col + 1, sticky="ew", padx=(0, 24), pady=5)
            self.vars[key], self.combos[key] = var, combo
        mapping.columnconfigure(1, weight=1)
        mapping.columnconfigure(3, weight=1)
        self.info = ttk.Label(frame, style="Muted.TLabel", wraplength=950)
        self.info.pack(anchor="w", pady=12)
        preview_frame = ttk.Frame(frame)
        preview_frame.pack(fill="both", expand=True)
        self.preview = ttk.Treeview(preview_frame, show="headings", height=6)
        self.preview.pack(fill="both", expand=True)
        sx = ttk.Scrollbar(preview_frame, orient="horizontal", command=self.preview.xview)
        sx.pack(fill="x")
        self.preview.configure(xscrollcommand=sx.set)
        footer = ttk.Frame(frame)
        footer.pack(fill="x", pady=(16, 0))
        ttk.Label(footer, text="Tablica se samo čita. Redci s greškama ostaju vidljivi u pregledu.", style="Muted.TLabel").pack(side="left")
        ttk.Button(footer, text="Dodaj proizvode", style="Accent.TButton", command=self.accept).pack(side="right")
        self.read()

    def read(self):
        try:
            self.headers, self.data = read_table(self.path, self.sheet.get(), int(self.header.get()))
            suggested = suggest_mapping(self.headers)
            for key, combo in self.combos.items():
                combo.configure(values=[""] + self.headers)
                self.vars[key].set(suggested.get(key, ""))
            self.preview.delete(*self.preview.get_children())
            self.preview.configure(columns=[str(i) for i in range(len(self.headers))])
            for i, header in enumerate(self.headers):
                self.preview.heading(str(i), text=header)
                self.preview.column(str(i), width=155, stretch=False)
            for _, values in self.data[:8]:
                self.preview.insert("", "end", values=[values.get(h, "") for h in self.headers])
            self.info.configure(text=f"Pronađeno {len(self.data)} redaka. Provjerite predloženo mapiranje, osobito Akcija VPC i oznaku modela. Interna šifra nije isto što i proizvođački model.")
        except Exception as exc:
            self.headers, self.data = [], []
            messagebox.showerror("Tablica", str(exc), parent=self)

    def apply_profile(self):
        profile = self.profiles.get(self.profile.get())
        if not profile:
            return
        self.header.set(str(profile.get("header_row", 1)))
        self.read()
        missing = []
        for key, column in profile["mapping"].items():
            if key in self.vars:
                self.vars[key].set(column if column in self.headers else "")
                if column and column not in self.headers:
                    missing.append(column)
        if missing:
            messagebox.showwarning("Profil", "Ovi stupci nedostaju: " + ", ".join(missing), parent=self)

    def accept(self):
        try:
            if not self.headers:
                raise ValidationError("Prvo očitajte stupce.")
            mapping = {key: value.get() for key, value in self.vars.items()}
            products = make_products(self.path, self.sheet.get(), self.data, mapping, self.app.settings)
            if self.profile.get().strip():
                self.profiles[self.profile.get().strip()] = {"mapping": mapping, "header_row": int(self.header.get())}
                self.app.store.set_setting("profiles", self.profiles)
            self.app.add_products(products)
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Mapiranje", str(exc), parent=self)


class SettingsDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Postavke programa")
        self.geometry("850x800")
        self.minsize(760, 700)
        self.transient(app)
        self.grab_set()
        body = ttk.Frame(self, padding=20)
        body.pack(fill="both", expand=True)
        tabs = ttk.Notebook(body)
        tabs.pack(fill="both", expand=True)
        price = ttk.Frame(tabs, padding=20)
        ai = ttk.Frame(tabs, padding=20)
        out = ttk.Frame(tabs, padding=20)
        tabs.add(price, text="Cijene")
        tabs.add(ai, text="Istraživanje i API")
        tabs.add(out, text="Izvoz i kategorije")
        self.vars = {}
        def entry(parent, key, label, values=None):
            ttk.Label(parent, text=label).pack(anchor="w", pady=(10, 4))
            var = tk.StringVar(value=str(getattr(app.settings, key)))
            widget = ttk.Combobox(parent, textvariable=var, values=values, state="readonly") if values else ttk.Entry(parent, textvariable=var)
            widget.pack(fill="x")
            self.vars[key] = var
        ttk.Label(price, text="Sve izlazne cijene uključuju PDV", style="Heading.TLabel").pack(anchor="w", pady=(0, 12))
        entry(price, "vat", "PDV (%)")
        self.gross = tk.BooleanVar(value=app.settings.input_gross)
        ttk.Checkbutton(price, text="Ulazni VPC i Akcija VPC već uključuju PDV", variable=self.gross).pack(anchor="w", pady=16)
        self.price_mode = tk.StringVar(value=app.settings.price_mode)
        ttk.Radiobutton(price, text="Prednost Akcija VPC, inače VPC → jedna prodajna cijena", variable=self.price_mode, value="preferred").pack(anchor="w", pady=6)
        ttk.Radiobutton(price, text="VPC → redovna, Akcija VPC → akcijska cijena", variable=self.price_mode, value="sale").pack(anchor="w", pady=6)
        ttk.Label(price, text="Primjer za ulaz bez PDV-a: VPC 100 €, Akcija VPC 80 €, PDV 25%.\nPrvi način: prodajna 100,00 €. Drugi način: redovna 125,00 €, akcijska 100,00 €.\n\nAko postoji samo akcijska VPC, ona postaje jedina prodajna cijena.\nAko je akcijska ćelija prazna, koristi se VPC. Neispravna vrijednost znači preskakanje.\n\nIzračun ne dodaje maržu. Zaokruživanje: dvije decimale, pola centa prema gore.\nSpremanje postavki ponovno računa cijene i poništava potvrdu izmijenjenih redaka.", wraplength=690, style="Muted.TLabel").pack(anchor="w", pady=20)
        ttk.Label(ai, text="OpenAI API ključ", style="Heading.TLabel").pack(anchor="w")
        self.key = tk.StringVar(value=app.api_key)
        ttk.Entry(ai, textvariable=self.key, show="•").pack(fill="x", pady=8)
        self.remember = tk.BooleanVar(value=app.key_path.exists())
        ttk.Checkbutton(ai, text="Zapamti ključ na ovom Windows korisničkom računu (šifrirano)", variable=self.remember).pack(anchor="w")
        ttk.Label(ai, text="Ključ unesite ovdje. Ne uključuje se u spremljeni projekt ni log. Na drugom računalu unesite ga ponovno.\nAPI pozivi i web pretraga naplaćuju se na API računu. Naziv, model i EAN šalju se API-ju; VPC se ne šalje.", wraplength=700, style="Muted.TLabel").pack(anchor="w", pady=10)
        entry(ai, "model", "Model za istraživanje", ["gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"])
        entry(ai, "limit", "Najviše proizvoda po pokretanju istraživanja (1–5000)")
        ttk.Label(ai, text="Proizvođačke domene (zarezom; prazno = pronađi proizvođača)").pack(anchor="w", pady=(16, 4))
        self.domains = scroll_text(ai, 3)
        self.domains.insert("1.0", app.settings.domains)
        ttk.Label(ai, text="Primjer oblika: proizvodac.hr, proizvodac.com\nRezultati pretrage uvijek traže pregled točnog modela, varijante, izvora i slika.\nIzravni URL bez AI-ja radi bez API ključa, ako stranica nudi Product podatke.", wraplength=700, style="Muted.TLabel").pack(anchor="w", pady=8)
        entry(out, "batch_size", "Proizvoda u jednom CSV-u (1–1000)")
        entry(out, "delimiter", "CSV razdjelnik (WooCommerce zadano: zarez)", [",", ";"])
        entry(out, "default_category", "Zadana kategorija ako nije u Excelu (neobavezno)")
        ttk.Label(out, text="Dopuštene kategorije: jedna po retku; hijerarhija npr. Dom > Usisavači").pack(anchor="w", pady=(18, 4))
        self.categories = scroll_text(out, 8)
        self.categories.insert("1.0", app.settings.categories)
        ttk.Label(out, text="CSV koristi UTF-8 s BOM oznakom i decimalnu točku. Za Excel koristite Podaci > Iz teksta/CSV.\nWooCommerce mora biti podešen na unos cijena s uključenim porezom.\nNovi proizvodi uvoze se kao nacrti. Ažuriranje ne mijenja postojeći status i zalihe.\nPrazna akcijska cijena ne briše postojeću akciju.", wraplength=700, style="Muted.TLabel").pack(anchor="w", pady=12)
        footer = ttk.Frame(body)
        footer.pack(fill="x", pady=(16, 0))
        ttk.Button(footer, text="Spremi postavke", style="Accent.TButton", command=self.save).pack(side="right")

    def save(self):
        try:
            values = asdict(self.app.settings)
            values.update({key: var.get() for key, var in self.vars.items()})
            values.update(input_gross=self.gross.get(), price_mode=self.price_mode.get(), domains=self.domains.get("1.0", "end-1c").strip(), categories=self.categories.get("1.0", "end-1c").strip())
            for key in ("limit", "batch_size"):
                values[key] = int(values[key])
            settings = Settings(**values)
            settings.validate()
            domain_list(settings.domains)
            if self.remember.get() and self.key.get().strip():
                self.app.key_path.write_bytes(protect(self.key.get().strip().encode()))
            elif self.app.key_path.exists():
                self.app.key_path.unlink()
            self.app.api_key = self.key.get().strip()
            self.app.settings = settings
            self.app.store.set_setting("settings", asdict(settings))
            self.app.reprice()
            self.app.log("Postavke spremljene.")
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Postavke", str(exc), parent=self)


class App(tk.Tk):
    MODES = {"Svi za novi unos": "all", "Samo novi": "new", "Samo ažuriranje": "update", "Odvojeno novi i ažuriranje": "split"}

    def __init__(self, folder=None):
        super().__init__()
        self.title("e·Point CSV Studio")
        self.geometry(f"{min(1380, self.winfo_screenwidth()-40)}x{min(880, self.winfo_screenheight()-80)}")
        self.minsize(1100, 720)
        self.configure(bg=BG)
        self.folder = Path(folder) if folder else data_folder()
        self.folder.mkdir(parents=True, exist_ok=True)
        self.store = Store(self.folder / "radni-katalog.epcsv")
        self.settings = Settings(**self.store.get_setting("settings", {}))
        self.products = self.store.load()
        self.key_path = self.folder / "api-key.dpapi"
        self.api_key = ""
        if self.key_path.exists():
            try:
                self.api_key = protect(self.key_path.read_bytes(), decrypt=True).decode()
            except Exception:
                pass
        self.catalog = None
        self.current = None
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.controls = []
        self.editor_controls = []
        self._build()
        self.refresh()
        self.poll_id = self.after(120, self.poll)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.log(f"Spremno. Lokalni podaci: {self.folder}")
        if self.products:
            self.log(f"Nastavljena prethodna obrada: {len(self.products)} proizvoda.")

    def _build(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), background=BG, foreground=INK)
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG)
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Heading.TLabel", font=("Segoe UI Semibold", 15), foreground=INK)
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 25), foreground=INK)
        style.configure("TButton", padding=(13, 8), background="#e6ebf1", foreground=INK, borderwidth=0, relief="flat")
        style.map("TButton", background=[("active", GLASS_HOVER), ("disabled", "#eef1f4")], foreground=[("disabled", "#97a1ad")])
        style.configure("Accent.TButton", background=ACCENT, foreground="white", font=("Segoe UI Semibold", 10))
        style.map("Accent.TButton", background=[("active", "#066b76"), ("disabled", "#97b7bb")], foreground=[("disabled", "white")])
        style.configure("TEntry", fieldbackground="#ffffff", foreground=INK, insertcolor=ACCENT, bordercolor=GLASS_EDGE, lightcolor=ACCENT, darkcolor=GLASS_EDGE)
        style.configure("TCombobox", fieldbackground="#ffffff", foreground=INK, selectbackground="#d4ebef", selectforeground=INK, bordercolor=GLASS_EDGE, lightcolor=ACCENT, darkcolor=GLASS_EDGE)
        style.configure("Treeview", rowheight=32, fieldbackground=PANEL, background=PANEL, foreground=INK, borderwidth=0)
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10), padding=8, background="#e7edf4", foreground=INK)
        style.map("Treeview", background=[("selected", "#d4ebef")], foreground=[("selected", INK)])
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", padding=(18, 9), background=GLASS, foreground=MUTED)
        style.map("TNotebook.Tab", background=[("selected", "#e7f2f4"), ("active", GLASS_HOVER)], foreground=[("selected", ACCENT)])
        style.configure("TCheckbutton", background=BG, foreground=INK)
        style.configure("TRadiobutton", background=BG, foreground=INK)
        style.configure("TProgressbar", background=ACCENT, troughcolor="#dbe2eb", bordercolor=GLASS_EDGE, lightcolor=ACCENT, darkcolor=ACCENT)
        outer = ttk.Frame(self, padding=(24, 18))
        outer.pack(fill="both", expand=True)
        top = ttk.Frame(outer)
        top.pack(fill="x")
        ttk.Label(top, text="e·Point CSV Studio", style="Title.TLabel").pack(side="left")
        self.button(top, "Postavke", lambda: self.settings_dialog()).pack(side="right")
        self.button(top, "Upute", self.help).pack(side="right", padx=8)
        ttk.Label(outer, text="Excel  →  proizvođački podaci  →  pregled  →  WooCommerce CSV", style="Muted.TLabel").pack(anchor="w", pady=(2, 18))
        bar = ttk.Frame(outer)
        bar.pack(fill="x")
        self.button(bar, "1  Učitaj Excel / CSV", self.import_file, accent=True).pack(side="left")
        self.button(bar, "WooCommerce katalog", self.import_catalog).pack(side="left", padx=8)
        self.button(bar, "Spremi projekt", self.save_project).pack(side="left", padx=(0, 8))
        self.button(bar, "Otvori projekt", self.open_project).pack(side="left")
        self.button(bar, "Nova obrada", self.new_project).pack(side="right")
        self.catalog_label = ttk.Label(outer, text="Postojeći WooCommerce katalog nije učitan. Za ažuriranje učitajte njegov CSV izvoz.", style="Muted.TLabel")
        self.catalog_label.pack(anchor="w", pady=(8, 14))
        actions = ttk.Frame(outer)
        actions.pack(fill="x")
        self.method = tk.StringVar(value="Tokenless preglednik")
        method_widget = ttk.Combobox(actions, textvariable=self.method, values=["Tokenless preglednik", "AI istraživanje", "Izravni URL bez AI-ja", "Provjeri slike"], state="readonly", width=24)
        method_widget.pack(side="left")
        self.controls.append(method_widget)
        self.button(actions, "2  Obradi nepotvrđene", self.run_research, accent=True).pack(side="left", padx=8)
        self.stop_btn = ttk.Button(actions, text="Zaustavi", command=self.cancel_job, state="disabled")
        self.stop_btn.pack(side="left")
        ttk.Label(actions, text="Prikaz").pack(side="left", padx=(24, 8))
        self.filter = tk.StringVar(value="Svi")
        filter_widget = ttk.Combobox(actions, textvariable=self.filter, values=["Svi", "Čeka obradu", "Za pregled", "Potvrđeno", "Preskočeno"], state="readonly", width=16)
        filter_widget.pack(side="left")
        filter_widget.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        self.search = tk.StringVar()
        ttk.Entry(actions, textvariable=self.search, width=22).pack(side="right")
        ttk.Label(actions, text="Traži naziv / SKU  ").pack(side="right")
        self.search.trace_add("write", lambda *_: self.refresh())
        self.stats = ttk.Label(outer, style="Heading.TLabel")
        self.stats.pack(anchor="w", pady=(16, 10))
        panes = ttk.Panedwindow(outer, orient="horizontal")
        panes.pack(fill="both", expand=True)
        left = ttk.Frame(panes)
        right = ttk.Frame(panes, padding=(14, 0, 0, 0))
        panes.add(left, weight=3)
        panes.add(right, weight=2)
        cols = ("row", "name", "price", "sale", "status")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
        for key, label, width in [("row", "Redak", 55), ("name", "Proizvod", 280), ("price", "Cijena €", 88), ("sale", "Akcija €", 88), ("status", "Status", 118)]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=45, stretch=key == "name")
        self.tree.tag_configure("error", foreground="#b33d32")
        self.tree.tag_configure("ok", foreground="#14744a")
        sy = ttk.Scrollbar(left, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sy.set)
        sy.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.select_product)
        self.detail_title = ttk.Label(right, text="Odaberite proizvod za pregled", style="Heading.TLabel", wraplength=450)
        self.detail_title.pack(anchor="w", pady=(0, 8))
        editor_tabs = ttk.Notebook(right)
        editor_tabs.pack(fill="both", expand=True)
        basics = ttk.Frame(editor_tabs, padding=10)
        descriptions = ttk.Frame(editor_tabs, padding=10)
        sources = ttk.Frame(editor_tabs, padding=10)
        editor_tabs.add(basics, text="Podaci i cijene")
        editor_tabs.add(descriptions, text="Opisi")
        editor_tabs.add(sources, text="Izvor i slike")
        basic_canvas = tk.Canvas(basics, bg=BG, highlightthickness=0)
        basic_scroll = ttk.Scrollbar(basics, orient="vertical", command=basic_canvas.yview)
        basic_canvas.configure(yscrollcommand=basic_scroll.set)
        basic_scroll.pack(side="right", fill="y")
        basic_canvas.pack(side="left", fill="both", expand=True)
        basics = ttk.Frame(basic_canvas)
        basic_window = basic_canvas.create_window((0, 0), window=basics, anchor="nw")
        basics.bind("<Configure>", lambda e: basic_canvas.configure(scrollregion=basic_canvas.bbox("all")))
        basic_canvas.bind("<Configure>", lambda e: basic_canvas.itemconfigure(basic_window, width=e.width))
        self.entries = {}
        for key, label, row, col, span in [("name", "Naziv", 0, 0, 3), ("sku", "SKU", 1, 0, 1), ("ean", "EAN / GTIN", 1, 2, 1),
                ("model", "Model", 2, 0, 1), ("brand", "Brend", 2, 2, 1), ("category", "Kategorija", 3, 0, 3),
                ("vpc", "VPC", 4, 0, 1), ("promo_vpc", "Akcija VPC", 4, 2, 1)]:
            ttk.Label(basics, text=label).grid(row=row, column=col, sticky="w", pady=4, padx=(0 if col == 0 else 8, 8))
            var = tk.StringVar()
            entry = ttk.Entry(basics, textvariable=var, width=12)
            entry.grid(row=row, column=col + 1, columnspan=span, sticky="ew", pady=4)
            self.entries[key] = var
            self.editor_controls.append(entry)
        basics.columnconfigure(1, weight=1)
        basics.columnconfigure(3, weight=1)
        self.price_label = ttk.Label(basics, style="Muted.TLabel", wraplength=420)
        self.price_label.grid(row=5, column=0, columnspan=4, sticky="w", pady=10)
        ttk.Label(descriptions, text="Kratki opis (hrvatski, običan tekst)").pack(anchor="w")
        self.short_text = scroll_text(descriptions, 3)
        ttk.Label(descriptions, text="Dugi opis (odlomci; HTML se izrađuje pri izvozu)").pack(anchor="w")
        self.desc_text = scroll_text(descriptions, 6)
        ttk.Label(descriptions, text="Specifikacije: naziv TAB vrijednost, jedan redak po specifikaciji").pack(anchor="w")
        self.spec_text = scroll_text(descriptions, 3)
        ttk.Label(sources, text="Proizvođačka stranica").pack(anchor="w")
        self.source_var = tk.StringVar()
        entry = ttk.Entry(sources, textvariable=self.source_var)
        entry.pack(fill="x", pady=6)
        self.editor_controls.append(entry)
        self.button(sources, "Otvori izvor u pregledniku", self.open_source).pack(anchor="w", pady=4)
        ttk.Label(sources, text="Izravni URL-ovi slika, svaki u zasebnom retku").pack(anchor="w", pady=(8, 0))
        self.images_text = scroll_text(sources, 4)
        self.button(sources, "Otvori prvu sliku", self.open_image).pack(anchor="w")
        ttk.Label(sources, text="Dokaz identiteta / napomene").pack(anchor="w", pady=(8, 0))
        self.evidence_text = scroll_text(sources, 4)
        self.evidence_text.configure(state="disabled")
        for tab in (descriptions, sources):
            tab.columnconfigure(0, weight=1)
            children = tab.winfo_children()
            for widget in children:
                widget.pack_forget()
            for row, widget in enumerate(children):
                expandable = isinstance(widget, ttk.Frame)
                widget.grid(row=row, column=0, sticky="nsew" if expandable else "ew", pady=3)
                if expandable:
                    tab.rowconfigure(row, weight=1)
        self.editor_controls.extend([self.short_text, self.desc_text, self.spec_text, self.images_text])
        review_footer = ttk.Frame(right)
        review_footer.pack(side="bottom", fill="x", before=editor_tabs)
        self.problem = ttk.Label(review_footer, text="", foreground="#ab352b", wraplength=450)
        self.problem.pack(fill="x", pady=6)
        review_bar = ttk.Frame(review_footer)
        review_bar.pack(fill="x")
        self.button(review_bar, "Spremi izmjene", self.save_editor).pack(side="left")
        self.button(review_bar, "Ponovi", lambda: self.run_research(selected_only=True)).pack(side="left", padx=5)
        self.button(review_bar, "3  Potvrdi i dalje", self.approve_current, accent=True).pack(side="right")
        bottom = ttk.Frame(outer)
        bottom.pack(side="bottom", fill="x", before=panes)
        footer = ttk.Frame(bottom)
        footer.pack(fill="x", pady=(16, 6))
        self.mode = tk.StringVar(value=next(k for k, v in self.MODES.items() if v == self.settings.export_mode))
        mode_combo = ttk.Combobox(footer, textvariable=self.mode, values=list(self.MODES), state="readonly", width=30)
        mode_combo.pack(side="left")
        self.controls.append(mode_combo)
        ttk.Label(footer, text="Izvoze se samo potvrđeni i valjani proizvodi.", style="Muted.TLabel").pack(side="left", padx=12)
        self.button(footer, "4  Izradi WooCommerce CSV", self.export, accent=True).pack(side="right")
        self.progress = ttk.Progressbar(bottom, mode="determinate")
        self.progress.pack(fill="x", pady=6)
        self.progress_label = ttk.Label(bottom, text="Spremno za rad", style="Muted.TLabel")
        self.progress_label.pack(anchor="w")
        self.log_text = tk.Text(bottom, height=2, font=("Consolas", 9), bg="#e9eef4", fg=MUTED, bd=0, padx=8, pady=6, state="disabled")
        self.log_text.pack(fill="x", pady=(6, 0))

    def button(self, parent, text, command, accent=False):
        b = ttk.Button(parent, text=text, command=command, style="Accent.TButton" if accent else "TButton")
        self.controls.append(b)
        return b

    def log(self, text):
        text = str(text).replace("\r", " ")
        if self.api_key:
            text = text.replace(self.api_key, "[skriveno]")
        line = f"{now()} | {text}\n"
        with (self.folder / "log.txt").open("a", encoding="utf-8") as file:
            file.write(line)
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def refresh(self):
        if not hasattr(self, "tree"):
            return
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        query, status = self.search.get().casefold(), self.filter.get()
        for p in self.products:
            if (status != "Svi" and p.status != status) or query not in (p.name + " " + p.sku).casefold():
                continue
            self.tree.insert("", "end", iid=p.uid, values=(p.row, p.name, p.regular, p.sale, p.status), tags=("ok" if p.approved else "error" if p.error else "normal",))
        if selected and self.tree.exists(selected[0]):
            self.tree.selection_set(selected[0])
        self.stats.configure(text=f"{len(self.products)} proizvoda    ·    {sum(p.approved for p in self.products)} potvrđeno    ·    {sum(bool(p.error) for p in self.products)} s greškom")

    def select_product(self, event=None):
        selection = self.tree.selection()
        if not selection or selection[0] == self.current:
            return
        if self.current and not self.busy:
            if not self.save_editor(refresh=False):
                self.tree.selection_set(self.current)
                return
        self.current = selection[0]
        self.fill_editor()

    def get_current(self):
        return next((p for p in self.products if p.uid == self.current), None)

    def fill_editor(self):
        p = self.get_current()
        if not p:
            self.detail_title.configure(text="Odaberite proizvod za pregled")
            for value in self.entries.values():
                value.set("")
            self.source_var.set("")
            self.price_label.configure(text="")
            self.problem.configure(text="")
        else:
            self.detail_title.configure(text=p.name)
            for key, var in self.entries.items():
                var.set(getattr(p, key))
            self.source_var.set(p.source_url)
            self.price_label.configure(text=f"S PDV-om: {p.regular or '—'} €" + (f"   Akcija: {p.sale} €" if p.sale else "") + f"\nOsnova: {p.price_source} | {p.origin}, redak {p.row}")
            self.problem.configure(text=p.error[:260] if p.error else "Prije potvrde provjerite model/varijantu, proizvođača, opise, kategoriju i slike.")
        values = [(self.short_text, p.short if p else ""), (self.desc_text, p.description if p else ""),
                  (self.spec_text, "\n".join(s["name"] + "\t" + s["value"] for s in p.specs) if p else ""),
                  (self.images_text, "\n".join(p.images) if p else ""), (self.evidence_text, p.evidence + "\n" + "\n".join(p.notes) if p else "")]
        for widget, value in values:
            widget.configure(state="normal")
            widget.delete("1.0", "end")
            widget.insert("1.0", value)
            widget.configure(state="disabled" if self.busy or widget == self.evidence_text else "normal")

    def save_editor(self, refresh=True):
        p = self.get_current()
        if not p or self.busy:
            return True
        updated = copy.deepcopy(p)
        for key, var in self.entries.items():
            setattr(updated, key, var.get().strip())
        updated.source_url = self.source_var.get().strip()
        updated.short = self.short_text.get("1.0", "end-1c").strip()
        updated.description = self.desc_text.get("1.0", "end-1c").strip()
        updated.images = parse_images(self.images_text.get("1.0", "end-1c"))
        specs = []
        for line in self.spec_text.get("1.0", "end-1c").splitlines():
            if line.strip():
                parts = line.split("\t", 1)
                if len(parts) != 2:
                    messagebox.showerror("Specifikacije", "Svaka specifikacija treba naziv i vrijednost odvojene tipkom TAB.")
                    return False
                original = next((s for s in p.specs if s["name"] == parts[0].strip() and s["value"] == parts[1].strip()), {})
                specs.append({"name": parts[0].strip(), "value": parts[1].strip(), "quote": original.get("quote", "")})
        updated.specs = specs
        if asdict(updated) == asdict(p):
            return True
        try:
            updated.regular, updated.sale, updated.price_source = calculate_prices(updated.vpc, updated.promo_vpc, self.settings)
            updated.status, updated.error = "Za pregled", ""
        except ValidationError as exc:
            updated.status, updated.error = "Preskočeno", str(exc)
        updated.approval = ""
        if updated.images != p.images:
            updated.checked_images, updated.image_checked_at = [], ""
        if any(getattr(updated, k) != getattr(p, k) for k in ("name", "model", "ean", "brand", "source_url")):
            updated.evidence = "Identitet ili URL je ručno promijenjen. Ponovno provjerite izvor."
            updated.researched_at = ""
        self.products[self.products.index(p)] = updated
        self.store.put(updated)
        if refresh:
            self.refresh()
            self.fill_editor()
        return True

    def approve_current(self):
        if not self.save_editor():
            return
        p = self.get_current()
        if not p:
            return
        try:
            if any(other.uid != p.uid and ((p.sku and other.sku.casefold() == p.sku.casefold()) or (p.ean and other.ean == p.ean)) for other in self.products):
                raise ValidationError("Prvo ispravite duplikat SKU/EAN u katalogu.")
            if p.error:
                raise ValidationError(p.error)
            p.approve()
            self.store.put(p)
            children = list(self.tree.get_children())
            next_uid = children[children.index(p.uid) + 1] if p.uid in children and children.index(p.uid) + 1 < len(children) else None
            self.refresh()
            if next_uid and self.tree.exists(next_uid):
                self.tree.selection_set(next_uid)
                self.tree.see(next_uid)
            self.log(f"Potvrđeno: {p.name}")
        except ValidationError as exc:
            messagebox.showwarning("Potvrda proizvoda", str(exc))

    def add_products(self, products):
        self.save_editor()
        self.products.extend(products)
        mark_duplicates(self.products)
        self.store.replace(self.products)
        self.refresh()
        for p in products:
            if p.error:
                self.log(f"PRESKOČENO | {p.origin} | redak {p.row} | {p.name} | {p.error}")
        self.log(f"Učitano {len(products)} redaka. Cijene uključuju PDV {self.settings.vat}%.")

    def import_file(self):
        if not self.save_editor():
            return
        path = filedialog.askopenfilename(title="Odaberite dobavljačku tablicu", filetypes=[("Excel i CSV", "*.xlsx *.xlsm *.xls *.csv *.tsv")])
        if path:
            try:
                ImportDialog(self, path)
            except Exception as exc:
                messagebox.showerror("Učitavanje", str(exc))

    def import_catalog(self):
        path = filedialog.askopenfilename(title="Postojeći WooCommerce CSV izvoz", filetypes=[("CSV", "*.csv")])
        if path:
            try:
                self.catalog = Catalog.read(path)
                self.catalog_label.configure(text="Postojeći katalog: " + Path(path).name)
                self.log("Učitan postojeći WooCommerce katalog: " + Path(path).name)
            except Exception as exc:
                messagebox.showerror("Katalog", str(exc))

    def settings_dialog(self):
        if self.save_editor():
            SettingsDialog(self)

    def reprice(self):
        for p in self.products:
            old = p.fingerprint()
            try:
                p.regular, p.sale, p.price_source = calculate_prices(p.vpc, p.promo_vpc, self.settings)
                if p.fingerprint() != old:
                    p.approval, p.status = "", "Za pregled"
                if p.error and any(word in p.error.lower() for word in ("cijena", "vpc", "decimal")):
                    p.error = ""
            except ValidationError as exc:
                p.error, p.status, p.approval = str(exc), "Preskočeno", ""
            self.store.put(p)
        self.refresh()
        self.fill_editor()

    def set_busy(self, busy):
        self.busy = busy
        for control in self.controls:
            control.configure(state="disabled" if busy else "readonly" if isinstance(control, ttk.Combobox) else "normal")
        for control in self.editor_controls:
            control.configure(state="disabled" if busy else "normal")
        self.stop_btn.configure(state="normal" if busy else "disabled")

    def run_research(self, selected_only=False):
        if not self.save_editor():
            return
        method = self.method.get()
        candidates = [copy.deepcopy(p) for p in self.products if not p.approved and p.regular and not p.error]
        # Retry failed research, but do not process malformed prices or duplicates.
        if (method == "Provjeri slike" or selected_only) and self.get_current():
            candidates = [copy.deepcopy(self.get_current())]
        if selected_only and not self.get_current():
            return
        if method != "Provjeri slike" and not selected_only:
            candidates = [p for p in candidates if p.status != "Za pregled"]
        if selected_only:
            try:
                p = candidates[0]
                p.regular, p.sale, p.price_source = calculate_prices(p.vpc, p.promo_vpc, self.settings)
                if any(o.uid != p.uid and (o.sku.casefold() == p.sku.casefold() or (p.ean and o.ean == p.ean)) for o in self.products):
                    raise ValidationError("Prvo ispravite duplikate SKU/EAN.")
            except ValidationError as exc:
                messagebox.showerror("Ponovna obrada", str(exc))
                return
        candidates = candidates[:self.settings.limit]
        if not candidates:
            messagebox.showinfo("Obrada", "Nema proizvoda koji čekaju obradu. Za ispravak preskočenog retka uredite podatke i spremite ga. Proizvod za pregled već ima podatke; provjerite ga i potvrdite.")
            return
        if method == "AI istraživanje" and not self.api_key:
            messagebox.showinfo("API pristup", "Unesite OpenAI API ključ u Postavke. Za dohvat s već poznatog URL-a možete odabrati Izravni URL bez AI-ja.")
            self.settings_dialog()
            return
        if method == "AI istraživanje" and not messagebox.askokcancel("Pokretanje API istraživanja", f"Obradit će se najviše {len(candidates)} proizvoda modelom {self.settings.model}.\n\nAPI i web pretraga koriste naplatu vašeg API računa. Rezultati iz lokalne predmemorije ne traže novi AI poziv.\nLimit možete promijeniti u Postavkama."):
            return
        self.cancel.clear()
        self.set_busy(True)
        settings = copy.deepcopy(self.settings)
        api_key = self.api_key
        self.progress.configure(maximum=len(candidates), value=0)
        self.progress_label.configure(text="Obrada pokrenuta…")
        def work():
            completed = 0
            try:
                fetcher = Fetcher(self.cancel)
                provider = OpenAIResearch(api_key, settings, self.cancel, fetcher) if method == "AI istraživanje" else BrowserResearch(settings, self.cancel, fetcher) if method == "Tokenless preglednik" else None
                cache = ResearchCache(self.folder / "research-cache.sqlite")
                for i, p in enumerate(candidates):
                    if self.cancel.is_set():
                        break
                    self.events.put(("progress", i, f"{i+1}/{len(candidates)} · {p.name}"))
                    try:
                        if method == "Provjeri slike":
                            if not p.images:
                                raise ValidationError("Unesite barem jedan URL slike.")
                            p.checked_images = [fetcher.image(url) for url in p.images]
                            p.image_checked_at = now()
                            p.error, p.status, p.approval = "", "Za pregled", ""
                            result = p
                        else:
                            key = cache.key(p, settings, method)
                            result = None if selected_only else cache.get(key, p)
                            if result:
                                result.checked_images = [fetcher.image(url) for url in result.images]
                                result.image_checked_at = now()
                            else:
                            result = provider.research(p) if method in ("AI istraživanje", "Tokenless preglednik") else direct_research(p, fetcher)
                                cache.put(key, result)
                        self.store.put(result)
                        self.events.put(("product", result))
                        self.events.put(("log", f"ZA PREGLED | {p.origin} | redak {p.row} | {p.name}"))
                        completed += 1
                    except ApiFatal as exc:
                        self.events.put(("log", str(exc)))
                        self.events.put(("fatal", str(exc)))
                        break
                    except Cancelled:
                        break
                    except Exception as exc:
                        result = copy.deepcopy(p)
                        result.error = str(exc)[:500]
                        result.status, result.approval = "Preskočeno", ""
                        self.store.put(result)
                        self.events.put(("product", result))
                        self.events.put(("log", f"PRESKOČENO | {p.origin} | redak {p.row} | {p.name} | {result.error}"))
                    self.events.put(("progress", i+1, f"Obrađeno {i+1}/{len(candidates)}. Uspješno: {completed}."))
            except Exception as exc:
                self.events.put(("fatal", str(exc)))
            finally:
                self.events.put(("done", "Obrada zaustavljena; dovršeni redci su spremljeni." if self.cancel.is_set() else f"Obrada završena. Uspješno: {completed}. Pregledajte rezultate i log."))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "product":
                    p = event[1]
                    index = next((i for i, old in enumerate(self.products) if old.uid == p.uid), None)
                    if index is not None:
                        self.products[index] = p
                    self.refresh()
                    self.fill_editor()
                elif event[0] == "progress":
                    self.progress.configure(value=event[1])
                    self.progress_label.configure(text=event[2])
                elif event[0] == "log":
                    self.log(event[1])
                elif event[0] == "fatal":
                    self.log(event[1])
                    messagebox.showerror("Obrada zaustavljena", event[1])
                elif event[0] == "done":
                    self.set_busy(False)
                    self.progress_label.configure(text=event[1])
                    self.log(event[1])
                    self.fill_editor()
        except queue.Empty:
            pass
        self.poll_id = self.after(120, self.poll)

    def destroy(self):
        if getattr(self, "poll_id", None):
            self.after_cancel(self.poll_id)
            self.poll_id = None
        super().destroy()

    def report_callback_exception(self, exc_type, exc, traceback):
        message = str(exc)
        if self.api_key:
            message = message.replace(self.api_key, "[skriveno]")
        try:
            self.log(f"Pogreška sučelja ({exc_type.__name__}): {message}")
        except OSError:
            pass
        messagebox.showerror("Radnja nije dovršena", message, parent=self)

    def cancel_job(self):
        self.cancel.set()
        self.progress_label.configure(text="Zaustavljanje… Čekam završetak aktivnog mrežnog zahtjeva (API najviše 180 s).")
        self.stop_btn.configure(state="disabled")

    def export(self):
        if not self.save_editor():
            return
        self.settings.export_mode = self.MODES[self.mode.get()]
        if self.settings.export_mode != "all" and self.catalog is None:
            messagebox.showinfo("Postojeći katalog", "Prvo učitajte CSV izvoz postojećih WooCommerce proizvoda.")
            return
        if not any(p.approved for p in self.products):
            messagebox.showinfo("Izvoz", "Prvo pregledajte i potvrdite barem jedan proizvod.")
            return
        directory = filedialog.askdirectory(title="Mapa za WooCommerce CSV i izvještaj")
        if directory:
            try:
                folder, summary = export_products(self.products, directory, self.settings, self.catalog)
                self.store.set_setting("settings", asdict(self.settings))
                self.log(f"IZVOZ | {summary['izvezeno']} proizvoda | {summary['preskoceno']} preskočeno | {folder}")
                messagebox.showinfo("Izvoz dovršen", f"Izvezeno: {summary['izvezeno']}\nPreskočeno: {summary['preskoceno']}\nCSV datoteka: {len(summary['csv'])}\n\n{folder}\n\nPročitajte UPUTE.txt. Sve cijene uključuju PDV.")
                os.startfile(folder)
            except Exception as exc:
                self.log("Izvoz nije dovršen: " + str(exc))
                messagebox.showerror("Izvoz", str(exc))

    def save_project(self):
        if not self.save_editor():
            return
        path = filedialog.asksaveasfilename(title="Spremi projekt", defaultextension=".epcsv", filetypes=[("ePoint CSV projekt", "*.epcsv")])
        if path:
            try:
                if Path(path).resolve() == self.store.path.resolve():
                    raise ValidationError("Odaberite drugi naziv za kopiju projekta.")
                self.store.backup(path)
                self.log("Projekt spremljen: " + path)
            except Exception as exc:
                messagebox.showerror("Projekt", str(exc))

    def archive_current(self):
        directory = self.folder / "arhiva"
        directory.mkdir(exist_ok=True)
        from uuid import uuid4
        path = directory / ("projekt-" + now().replace(":", "-") + "-" + uuid4().hex[:6] + ".epcsv")
        self.store.backup(path)
        return path

    def open_project(self):
        if not self.save_editor():
            return
        path = filedialog.askopenfilename(title="Otvori spremljeni projekt", filetypes=[("ePoint CSV projekt", "*.epcsv")])
        if path:
            try:
                import sqlite3
                with database(Path(path).as_uri() + "?mode=ro", uri=True) as db:
                    products = [Product(**json.loads(r[0])) for r in db.execute("SELECT body FROM products ORDER BY rowid")]
                    row = db.execute("SELECT body FROM settings WHERE name='settings'").fetchone()
                    settings = Settings(**json.loads(row[0])) if row else self.settings
                    settings.validate()
                archive = self.archive_current()
                self.store.replace(products)
                self.products, self.settings, self.current = products, settings, None
                self.store.set_setting("settings", asdict(settings))
                self.catalog = None
                self.catalog_label.configure(text="Ponovno učitajte aktualni WooCommerce katalog za provjeru postojećih proizvoda.")
                self.mode.set(next(k for k, v in self.MODES.items() if v == settings.export_mode))
                self.refresh()
                self.fill_editor()
                self.log(f"Projekt otvoren. Prethodni projekt spremljen: {archive}")
            except Exception as exc:
                messagebox.showerror("Projekt", str(exc))

    def new_project(self):
        if not self.save_editor():
            return
        archive = self.archive_current()
        self.products, self.current = [], None
        self.store.replace([])
        self.refresh()
        self.fill_editor()
        self.log("Nova obrada. Prethodna je spremljena u " + str(archive))

    def open_source(self):
        try:
            webbrowser.open(public_url(self.source_var.get().strip()))
        except Exception as exc:
            messagebox.showerror("Izvor", str(exc))

    def open_image(self):
        try:
            urls = parse_images(self.images_text.get("1.0", "end-1c"))
            if not urls:
                raise ValidationError("Nema slike.")
            webbrowser.open(public_url(urls[0]))
        except Exception as exc:
            messagebox.showerror("Slika", str(exc))

    def help(self):
        window = tk.Toplevel(self)
        window.title("Kako koristiti CSV Studio")
        window.geometry("820x690")
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill="both", expand=True)
        text = scroll_text(frame, 25)
        text.insert("1.0", HELP)
        text.configure(state="disabled")

    def close(self):
        if self.busy:
            self.cancel_job()
            messagebox.showinfo("Obrada se zaustavlja", "Dovršeni redci su spremljeni. Pričekajte završetak aktivnog zahtjeva pa zatvorite program.")
            return
        if self.save_editor():
            self.destroy()


HELP = """1. UČITAJTE TABLICU
Odaberite .xlsx, .xlsm, .xls ili UTF-8 CSV. Odaberite list i redak zaglavlja.
Provjerite mapiranje naziva i cijena; šifra artikla i proizvođački model su različita polja. Mapiranje spremite kao profil dobavljača. Više učitavanja dodaje proizvode u isti katalog.
Formula u Excelu mora imati spremljen izračun: ako nedostaje, otvorite tablicu u Excelu/LibreOfficeu, ponovno izračunajte i spremite.

2. POSTAVKE I CIJENE
Početno su VPC i Akcija VPC bez PDV-a; program dodaje 25%. Možete promijeniti postavku. Nema dodatne marže. Prednost ima Akcija VPC, inače VPC. Odaberite prikaz jedne cijene ili redovne i akcijske. Nejasne ili neispravne cijene preskaču se. Sve izlazne cijene su EUR s PDV-om.

3. ISTRAŽIVANJE
Tokenless preglednik: koristi lokalni Chromium kroz Playwright, bez OpenAI API-ja, tokena i troška po upitu. Za automatsko pronalaženje URL-a unesite proizvođačke domene; ako je URL već u tablici, preglednik otvara taj URL. CAPTCHA, robots/403/429 i nejasan model preskaču se za ručni pregled.
AI istraživanje: unesite svoj OpenAI API ključ u Postavke. Početni limit je 20 proizvoda po pokretanju; povećajte ga nakon probne obrade. API i web pretraga troše sredstva vašeg API računa. Korištenje ovog programa nije povezano s pretplatom na razgovor.
Za ograničenje izvora unesite proizvođačke domene. Ako ostanu prazne, AI traži službenog proizvođača, a vi provjeravate njegov prijedlog. Cijene i cijela Excel tablica ne šalju se AI-ju; šalju se naziv, model, brend, EAN, URL i dopuštene kategorije.
Izravni URL bez AI-ja: potreban je URL u tablici ili ručno unesen URL. Podržan je Product JSON-LD; opis ostaje na jeziku izvora. Ako je izvor dinamičan, blokiran, PDF ili nema podatke, proizvod se preskače. Program ne zaobilazi provjere pristupa.
Rezultati se spremaju nakon svakog proizvoda. Predmemorija vrijedi najviše 7 dana. Zaustavi prekida obradu nakon aktivnog zahtjeva. Pri pokretanju se vraća prethodni katalog.

4. PREGLED I POTVRDA
Odaberite redak. Uredite podatke, hrvatske opise, kategoriju i slike. Otvorite proizvođačku stranicu i provjerite točan model, kapacitet, boju, regiju i paket. Potvrda modela u tekstu ne dokazuje automatski svaku varijantu ni svaku rečenicu opisa.
Za ručno unesene slike odaberite Provjeri slike i Obradi nepotvrđene (provjerava odabrani redak). Kliknite Potvrdi i dalje. Svaka izmjena proizvoda poništava njegovu potvrdu. Nevaljani redci se ne izvoze.
Za ponavljanje neuspjelog istraživanja odaberite redak, način istraživanja i gumb Ponovi. Ponovi zanemaruje predmemoriju. Ne učitavajte duplikate u isti katalog.

5. POSTOJEĆI PROIZVODI
Iz WooCommercea izvezite postojeće proizvode u CSV i učitajte ga gumbom WooCommerce katalog. Program uspoređuje SKU i, ako je dostupan, EAN te izvozi stvarni postojeći SKU/ID. Sukobi i varijacije se preskaču.
Svi za novi unos: priprema novih nacrta; uz učitan katalog postojeći se preskaču.
Samo novi / Samo ažuriranje / Odvojeno: potreban je postojeći katalog. Ta datoteka je snimka; koristite svježi izvoz.

6. IZVOZ U WOOCOMMERCE
Izvoze se samo potvrđeni proizvodi. Svaki izvoz dobiva novu mapu, CSV datoteke u skupinama, izvori.csv, log.txt, izvjestaj.json i UPUTE.txt. U WordPress uvozite samo novi-*.csv ili azuriranje-*.csv.
Za nove isključite Ažuriraj postojeće proizvode, za ažuriranje uključite. Provjerite mapiranje stupaca, Brands i EAN. Nove stavke imaju status Nacrt. Ažuriranje ne mijenja status objave i zalihe. Prazna akcijska cijena NE uklanja postojeću akciju.
WooCommerce mora biti postavljen na unos cijena s uključenim porezom. Najprije probajte nekoliko proizvoda. Izvoz je UTF-8 BOM; u Excelu koristite Podaci > Iz teksta/CSV kako ne bi mijenjao SKU/EAN.

PROJEKTI I PRIJENOS
.epcsv projekt sadrži katalog i postavke, bez API ključa. Spremite ga za prijenos na drugo računalo. Nova obrada automatski arhivira prethodnu u data/arhiva. Program radi bez instalacije Pythona; podaci se spremaju u data uz EXE, ili LocalAppData/ePointCSV ako mapa nije zapisiva.

Verzija 1.0 podržava jednostavne proizvode (simple). Varijacije, zalihe, automatska objava i izravan pristup WordPressu nisu uključeni.
"""

