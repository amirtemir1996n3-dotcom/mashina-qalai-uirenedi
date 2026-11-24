"""Кітаптың Colab блокноттарын таза ортада іске қосып тексереді.

GitHub Actions айына бір рет (және блокноттар өзгергенде) іске қосады:
кітапханалар жаңарғанда бұзылған код бірден көрінеді.

Қолданылуы:
    python tools/run_notebooks.py vol1            # 1-томның барлық блокноты
    python tools/run_notebooks.py vol2 ch12 ch13  # 2-томның таңдалған блокноттары
"""
import os
import re
import sys
import shutil
import tempfile
import time
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError, CellTimeoutError

ROOT = Path(__file__).resolve().parent.parent
BOOKS = {"vol1": ROOT / "notebooks", "vol2": ROOT / "vol2" / "notebooks"}
CELL_TIMEOUT = 1800          # бір ұяшыққа ең көбі 30 минут

# «optional» белгісі бар ұяшықтар (файл жүктеу, input(), Ollama т.б.) әдепкіде
# өткізіледі. Мына ұяшықтар интерактивті емес, сондықтан оларды да тексереміз:
RUN_OPTIONAL = {("vol1", "ch21"): {0, 1, 2, 3, 4, 5, 6}}


def _text_fixture(work):
    """23-тарау: оқырман жүктейтін text.txt орнына 1-томның мәтінінің басы."""
    text = (ROOT / "data" / "kitap.txt").read_text(encoding="utf-8")[:60000]
    (work / "text.txt").write_text(text, encoding="utf-8")


FIXTURES = {("vol1", "ch23"): _text_fixture}


def prepare(book, name, nb):
    """Өткізілетін ұяшықтарды бос ұяшыққа ауыстырады."""
    allowed = RUN_OPTIONAL.get((book, name), set())
    skipped, k = 0, -1
    for cell in nb.cells:
        if cell.cell_type != "code":
            continue
        k += 1
        if "optional" in cell.metadata.get("tags", []) and k not in allowed:
            cell.source = "# автоматты тексеруде өткізілді (міндетті емес ұяшық)"
            skipped += 1
    return skipped


ANSI = re.compile(r"\x1b\[[0-9;]*m")


def run_one(book, path):
    name = path.stem
    nb = nbformat.read(path, as_version=4)
    skipped = prepare(book, name, nb)
    work = Path(tempfile.mkdtemp(prefix=f"{book}_{name}_"))
    if (book, name) in FIXTURES:
        FIXTURES[(book, name)](work)
    start = time.time()
    status, detail = "ok", ""
    try:
        NotebookClient(nb, timeout=CELL_TIMEOUT, kernel_name="python3",
                       resources={"metadata": {"path": str(work)}}).execute()
    except CellTimeoutError as e:
        status, detail = "уақыт бітті", str(e).strip().splitlines()[-1][:300]
    except CellExecutionError as e:
        status = "қате"
        lines = [l for l in str(e).strip().splitlines() if l.strip()]
        detail = lines[-1][:300] if lines else repr(e)
    except Exception as e:          # ядро құлады т.б.
        status, detail = "қате", f"{type(e).__name__}: {e}"[:300]
    finally:
        shutil.rmtree(work, ignore_errors=True)
    detail = ANSI.sub("", detail)
    return {"name": name, "status": status, "detail": detail,
            "sec": round(time.time() - start), "skipped": skipped}


def report(book, results):
    bad = [r for r in results if r["status"] != "ok"]
    head = (f"## {book}: {len(results) - len(bad)}/{len(results)} блокнот сәтті орындалды\n\n"
            if results else f"## {book}: блокнот табылмады\n\n")
    rows = ["| Блокнот | Нәтиже | Уақыт, с | Өткізілген ұяшық | Қате |", "|---|---|---|---|---|"]
    for r in results:
        detail = r["detail"].replace("|", "\\|").replace("\n", " ")
        mark = "✅" if r["status"] == "ok" else "❌ " + r["status"]
        rows.append(f"| {r['name']} | {mark} | {r['sec']} | {r['skipped']} | {detail} |")
    text = head + "\n".join(rows) + "\n"
    Path(f"report-{book}.md").write_text(text, encoding="utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)
    return not bad


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in BOOKS:
        sys.exit(__doc__)
    book, only = sys.argv[1], set(sys.argv[2:])
    paths = sorted(BOOKS[book].glob("ch*.ipynb")) + sorted(BOOKS[book].glob("kripto*.ipynb"))
    if only:
        paths = [p for p in paths if p.stem in only]
    results = []
    for path in paths:
        r = run_one(book, path)
        print(f"{r['name']}: {r['status']} ({r['sec']} с) {r['detail']}", flush=True)
        results.append(r)
    sys.exit(0 if report(book, results) and results else 1)


if __name__ == "__main__":
    main()
