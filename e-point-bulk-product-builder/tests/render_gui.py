"""Capture only the app's own window, populated with clearly synthetic QA rows."""
import tempfile
from pathlib import Path

from PIL import ImageGrab

from epoint_csv.ui import App, ImportDialog, SettingsDialog
from tests.test_core import product, xlsx_fixture


def main():
    output = Path("test-output")
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="epoint-visual-") as tmp:
        app = App(tmp)
        app.geometry("1380x880+20+20")
        products = []
        for i, name in enumerate(["TEST — Četka X100", "TEST — Usisavač V200", "TEST — Pametni sat S300", "TEST — Slušalice H400"]):
            p = product(name=name, sku=f"TEST-{i:03}", row=i+2, origin="TESTNI PODACI / Cjenik", model=f"X{i}00")
            p.status = "Potvrđeno" if i == 0 else "Za pregled" if i == 1 else "Čeka obradu" if i == 2 else "Preskočeno"
            if i:
                p.approval = ""
            if i == 3:
                p.error = "Testna greška: izvor ne potvrđuje točan model."
            products.append(p)
        app.add_products(products)
        app.tree.selection_set(products[1].uid)
        app.update()
        def snap(window, name):
            window.update()
            window.after(600, lambda: None)
            window.update_idletasks()
            x, y = window.winfo_rootx(), window.winfo_rooty()
            ImageGrab.grab(bbox=(x, y, x+window.winfo_width(), y+window.winfo_height())).save(output / name)
        # Tk's redraw has completed before capture.
        app.after(800, lambda: snap(app, "app.png"))
        def next_dialog():
            settings = SettingsDialog(app)
            settings.geometry("850x800+40+40")
            settings.update()
            app.after(600, lambda: snap(settings, "settings.png"))
            app.after(900, settings.destroy)
        app.after(1000, lambda: app.geometry("1100x720+20+20"))
        app.after(1600, lambda: snap(app, "app-small.png"))
        app.after(1900, next_dialog)
        app.after(3600, app.destroy)
        app.mainloop()
    print(output.resolve())


if __name__ == "__main__":
    main()

