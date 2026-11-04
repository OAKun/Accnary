"""Compare local HEAD with working-tree hot paths using fictional records only."""

from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
from statistics import median
import subprocess
import sys
import tempfile
from time import perf_counter
from types import ModuleType

frame_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(frame_dir))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication, QEvent

from app.models import Account, Catalog, Service
from app.services import CatalogService
from app.services.search_service import SearchIndex
from app.ui.main_window import MainWindow


def baseline_module(relative_path: str, name: str) -> ModuleType:
    source = subprocess.check_output(
        ["git", "show", f"HEAD:frame/{relative_path}"], cwd=frame_dir,
    ).decode("utf-8")
    module = ModuleType(name)
    module.__file__ = str(frame_dir / relative_path)
    sys.modules[name] = module
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


def elapsed_ms(operation, repeats: int = 5) -> float:
    durations = []
    for _ in range(repeats):
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        start = perf_counter()
        operation()
        durations.append((perf_counter() - start) * 1000)
    return round(median(durations), 3)


def main(counts: tuple[int, ...], output_path: Path) -> None:
    old_search = baseline_module("app/services/search_service.py", "benchmark_old_search")
    app = QApplication.instance() or QApplication([])
    results = []
    with tempfile.TemporaryDirectory(prefix="accnary-benchmark-") as temp_dir:
        os.environ["ACCNARY_SETTINGS_DIR"] = temp_dir
        catalog = CatalogService.create_vault(Path(temp_dir) / "fictional.kdbx", "fictional-benchmark-password")
        for count in counts:
            service = Service(
                name="Fictional platform", urls=["https://fictional.invalid/portal/login"],
                login_urls=["https://auth.fictional.invalid/login"],
                accounts=[Account(uuid=f"fictional-{i}", username=f"user{i:05d}") for i in range(count)],
            )
            model = Catalog(services=[service])
            old_index, new_index = old_search.SearchIndex(), SearchIndex()
            row = {"accounts": count}
            row["index_old_ms"] = elapsed_ms(lambda: old_index.build(model))
            row["index_new_ms"] = elapsed_ms(lambda: new_index.build(model))
            query = "https://fictional.invalid/portal/login"
            old_hits, new_hits = old_index.search(query), new_index.search(query)
            assert [(h.account.uuid, h.score, h.matched) for h in old_hits] == [
                (h.account.uuid, h.score, h.matched) for h in new_hits
            ]
            row["url_search_old_ms"] = elapsed_ms(lambda: old_index.search(query))
            row["url_search_new_ms"] = elapsed_ms(lambda: new_index.search(query))
            row["metadata_copy_old_ms"] = elapsed_ms(lambda: deepcopy(service))
            row["metadata_copy_new_ms"] = elapsed_ms(lambda: deepcopy(replace(service, accounts=[])))
            catalog.catalog = model
            catalog.search_index.build(model)
            window = MainWindow(catalog)
            row["list_refresh_ms"] = elapsed_ms(
                lambda: window._refresh_accounts(update_navigation=False)
            )
            results.append(row)
            # Lock before close so synthetic, unpersisted records cannot be saved.
            catalog.lock()
            window.close()
            window.deleteLater()
            app.processEvents()
            if count != counts[-1]:
                catalog = CatalogService.open(Path(temp_dir) / "fictional.kdbx", "fictional-benchmark-password")
    output_path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    counts = (2000, 10000)
    output_path = frame_dir / "docs" / "optimization-20261103.json"
    main(counts, output_path)
