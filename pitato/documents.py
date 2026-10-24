"""Documents to text (no extra packages needed)."""
import os
import re
import zipfile


# ---- documents to text (no extra packages needed) ---------------------------
def _xml(z, name):
    import xml.etree.ElementTree as ET
    return ET.fromstring(z.read(name))


def _numbered(names, pattern):
    found = [n for n in names if re.match(pattern, n)]
    return sorted(found, key=lambda n: int(re.findall(r"\d+", n.rsplit("/", 1)[-1])[0]))


def doc_text(path):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".rtf":
        raw = open(path, errors="ignore").read()
        raw = re.sub(r"\\par[d]?\b ?", "\n", raw)
        raw = re.sub(r"\{\\\*[^{}]*\}", "", raw)
        raw = re.sub(r"\\'[0-9a-f]{2}|\\[a-zA-Z]+-?\d* ?|[{}]", "", raw)
        return raw.strip()
    out = []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if ext == ".docx":
            W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
            for p in _xml(z, "word/document.xml").iter(W + "p"):
                parts = []
                for el in p.iter():
                    if el.tag == W + "t":
                        parts.append(el.text or "")
                    elif el.tag == W + "tab":
                        parts.append("    ")
                    elif el.tag in (W + "br", W + "cr"):
                        parts.append("\n")
                out.append("".join(parts))
        elif ext == ".pptx":
            A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
            for k, n in enumerate(_numbered(names, r"ppt/slides/slide\d+\.xml$"), 1):
                out += ["", f"── Slide {k} ──", ""]
                for p in _xml(z, n).iter(A + "p"):
                    line = "".join(t.text or "" for t in p.iter(A + "t"))
                    if line.strip():
                        out.append(line)
        elif ext == ".xlsx":
            S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
            shared = []
            if "xl/sharedStrings.xml" in names:
                shared = ["".join(t.text or "" for t in si.iter(S + "t"))
                          for si in _xml(z, "xl/sharedStrings.xml").iter(S + "si")]
            for k, n in enumerate(_numbered(names, r"xl/worksheets/sheet\d+\.xml$"), 1):
                out += ["", f"── Sheet {k} ──", ""]
                for row in _xml(z, n).iter(S + "row"):
                    cells = []
                    for c in row.iter(S + "c"):
                        v = c.find(S + "v")
                        if c.get("t") == "s" and v is not None:
                            cells.append(shared[int(v.text)])
                        elif c.get("t") == "inlineStr":
                            cells.append("".join(t.text or "" for t in c.iter(S + "t")))
                        else:
                            cells.append(v.text if v is not None and v.text else "")
                    out.append("  |  ".join(cells))
        elif ext in (".odt", ".odp", ".ods"):
            T = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
            TB = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
            root = _xml(z, "content.xml")
            if ext == ".ods":
                for r in root.iter(TB + "table-row"):
                    cells = ["".join(c.itertext()) for c in r.findall(TB + "table-cell")]
                    while cells and not cells[-1]:
                        cells.pop()
                    out.append("  |  ".join(cells))
            else:
                for el in root.iter():
                    if el.tag in (T + "p", T + "h"):
                        out.append("".join(el.itertext()))
        else:
            raise OSError("needs LibreOffice")
    return "\n".join(out).strip()
