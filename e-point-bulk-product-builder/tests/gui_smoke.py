"""Integration checks exercise the real Tk controls and product state on this machine."""
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from epoint_csv.core import Settings, export_products
from epoint_csv.ui import App, ImportDialog, SettingsDialog
from tests.test_core import product, xlsx_fixture


def main():
    with tempfile.TemporaryDirectory(prefix="epoint-gui-") as temp:
        folder = Path(temp)
        app = App(folder)
        app.update()
        path = folder / "fixture.xlsx"
        xlsx_fixture(path)
        dialog = ImportDialog(app, str(path))
        app.update()
        assert dialog.vars["name"].get() == "Naziv"
        assert dialog.vars["vpc"].get() == "VPC"
        dialog.accept()
        app.update()
        assert len(app.products) == 2
        assert app.products[0].regular == "125.00"
        assert app.products[1].error
        app.new_project()
        assert not app.products
        p = product()
        p.approval, p.status = "", "Za pregled"
        app.add_products([p])
        app.tree.selection_set(p.uid)
        app.update()
        assert app.current == p.uid
        assert app.entries["name"].get() == p.name
        app.short_text.delete("1.0", "end")
        app.short_text.insert("1.0", "Provjeren hrvatski opis čćšžđ.")
        app.save_editor()
        app.approve_current()
        app.update()
        assert app.products[0].approved
        app.entries["vpc"].set("120")
        app.save_editor()
        assert app.products[0].regular == "150.00"
        assert not app.products[0].approved
        app.approve_current()
        out, summary = export_products(app.products, folder / "output", app.settings)
        assert summary["izvezeno"] == 1
        settings = SettingsDialog(app)
        app.update()
        settings.vars["vat"].set("25")
        settings.price_mode.set("sale")
        settings.save()
        app.update()
        assert app.settings.price_mode == "sale"
        project = folder / "saved.epcsv"
        app.store.backup(project)
        with patch("epoint_csv.ui.filedialog.askopenfilename", return_value=str(project)):
            app.open_project()
        app.update()
        assert len(app.products) == 1
        app.destroy()
        resumed = App(folder)
        resumed.update()
        assert len(resumed.products) == 1
        resumed.destroy()
    print("GUI OK: Excel dialog, mapping, invalid row, archive, editing, approval, repricing, export, settings, project and restart")


if __name__ == "__main__":
    main()

