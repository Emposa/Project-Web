import os
import sys
from pathlib import Path


def main():
    if os.name == "nt":
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    from epoint_csv.ui import App
    folder = None
    if "--smoke-test" in sys.argv:
        import tempfile
        folder = Path(tempfile.mkdtemp(prefix="epoint-csv-smoke-"))
    app = App(folder)
    if "--smoke-test" in sys.argv:
        def smoke():
            from epoint_csv.core import Product, Settings, calculate_prices, export_products, now, read_table
            from jsonschema import validate
            from openpyxl import load_workbook
            import xlrd
            from epoint_csv.research import RESULT_SCHEMA
            assert calculate_prices("100", "80", Settings())[0] == "100.00"
            assert app.winfo_exists()
            if "--smoke-input" in sys.argv:
                path = sys.argv[sys.argv.index("--smoke-input") + 1]
                headers, rows = read_table(path)
                assert headers and rows
            p = Product(name="TEST X100", sku="SMOKE-1", regular="125.00", brand="TEST", category="TEST", short="Test čćšžđ", description="Testni opis", images=["https://example.com/test.png"], checked_images=["https://example.com/test.png"], image_checked_at=now())
            p.approve()
            _, summary = export_products([p], folder, Settings())
            assert summary["izvezeno"] == 1
            (folder / "smoke-ok.txt").write_text("GUI startup, Tcl/Tk, SQLite, Decimal, Excel reader, xlrd, JSON schema imports and CSV export OK", encoding="utf-8")
            app.destroy()
        app.after(800, smoke)
    app.mainloop()


if __name__ == "__main__":
    main()

