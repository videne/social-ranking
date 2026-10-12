#!/usr/bin/env python3
"""Adună toate exporturile CSV din instagram/ și tiktok/ într-un singur fișier site/data.json.

Rulează automat (GitHub Actions) la fiecare fișier nou urcat în repo.
Recunoaște două feluri de fișiere:
  - pe postare  (fiecare rând = o postare / un video)  -> intră în clasament
  - pe zi       (fiecare rând = o zi, totaluri de cont) -> rezumatul pe perioadă
Dacă aceeași postare apare în mai multe exporturi, se păstrează rândul cu cele mai multe vizualizări
(cifrele „lifetime” doar cresc, deci acela e cel mai nou).
"""
import csv, json, re, shutil, sys, unicodedata
from datetime import datetime, date, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "site"
TODAY = date.today()

SYN = {
    "id":       ["post id", "video id", "media id", "id"],
    "account":  ["account username", "username", "account"],
    "caption":  ["description", "caption", "video title", "title", "post title", "titlu", "descriere"],
    "link":     ["permalink", "video link", "post link", "link", "url"],
    "type":     ["post type", "media type", "type"],
    "date":     ["publish time", "post time", "posted time", "create time", "publish date", "date posted", "date", "data"],
    "views":    ["views", "video views", "total views", "plays", "total play", "vizualizari"],
    "reach":    ["reach", "accounts reached", "acoperire"],
    "likes":    ["likes", "total likes", "like", "aprecieri"],
    "comments": ["comments", "total comments", "comentarii"],
    "saves":    ["saves", "add to favorites", "favorites", "total favorites", "saved", "salvari"],
    "shares":   ["shares", "total shares", "distribuiri"],
    "follows":  ["follows", "new followers", "urmaritori noi"],
    "duration": ["duration (sec)", "duration", "video duration"],
}
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS.update({"ianuarie": 1, "februarie": 2, "martie": 3, "aprilie": 4, "mai": 5, "iunie": 6, "iulie": 7,
               "septembrie": 9, "octombrie": 10, "noiembrie": 11, "decembrie": 12})


def norm(s):
    s = unicodedata.normalize("NFD", str(s)).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9() ]", " ", s)).strip()


def map_headers(headers):
    n = [norm(h) for h in headers]
    out, used = {}, set()
    for key, syns in SYN.items():
        for s in syns:
            idx = next((i for i, h in enumerate(n) if i not in used and h == s), None)
            if idx is None and len(s) > 3:
                idx = next((i for i, h in enumerate(n) if i not in used and f" {s} " in f" {h} "), None)
            if idx is not None:
                out[key] = idx
                used.add(idx)
                break
    return out


def num(v):
    s = str(v or "").strip().replace(" ", "").replace(" ", "")
    if not s or s in "-–":
        return 0
    mult = 1
    if s[-1:] in "kK":
        mult, s = 1_000, s[:-1]
    elif s[-1:] in "mM":
        mult, s = 1_000_000, s[:-1]
    if re.fullmatch(r"-?\d{1,3}([.,]\d{3})+", s):
        s = re.sub(r"[.,]", "", s)
    else:
        s = s.replace(",", ".")
    try:
        return round(float(re.sub(r"[^\d.\-]", "", s)) * mult)
    except ValueError:
        return 0


def read_csv(path):
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-16", "cp1250", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    first = next((l for l in text.splitlines() if l.strip()), "")
    delim = max([",", ";", "\t"], key=first.count)
    rows = [r for r in csv.reader(text.splitlines(keepends=True), delimiter=delim) if any(c.strip() for c in r)]
    return rows


def slash_order(values):
    """Exporturile Meta folosesc LL/ZZ/AAAA. Dacă vreun prim câmp > 12, fișierul e ZZ/LL/AAAA."""
    for v in values:
        m = re.match(r"\s*(\d{1,2})[/.](\d{1,2})[/.](\d{4})", v or "")
        if m and int(m.group(1)) > 12:
            return "dmy"
    return "mdy"


def parse_dt(s, order="mdy"):
    s = (s or "").strip()
    if not s:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{1,2}):(\d{2}))?", s)
    if m:
        y, mo, d, h, mi = m.groups()
        return datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0))
    m = re.match(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})(?:[ ,]+(\d{1,2}):(\d{2}))?", s)
    if m:
        a, b, y, h, mi = m.groups()
        mo, d = (a, b) if order == "mdy" else (b, a)
        return datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0))
    if re.fullmatch(r"\d{10}", s):
        return datetime.fromtimestamp(int(s), tz=timezone.utc).replace(tzinfo=None)
    m = re.match(r"([A-Za-z]+)\.? (\d{1,2}),? (\d{4})", s) or None
    if m and norm(m.group(1)) in MONTHS:
        return datetime(int(m.group(3)), MONTHS[norm(m.group(1))], int(m.group(2)))
    m = re.match(r"(\d{1,2}) ([A-Za-zăâîșțĂÂÎȘȚ]+)\.?(?: (\d{4}))?$", s)
    if m and norm(m.group(2)) in MONTHS:
        return datetime(int(m.group(3) or 0) or 1, MONTHS[norm(m.group(2))], int(m.group(1)))
    return None


def fill_years(dates):
    """Fișierul Overview de TikTok are date fără an („31 December”). Ultima zi e cea mai recentă
    apariție a ei până azi; mergând înapoi, anul scade de fiecare dată când luna „crește”."""
    if not dates or all(d is None or d.year > 1 for d in dates):
        return dates
    last = dates[-1]
    year = TODAY.year if (last.month, last.day) <= (TODAY.month, TODAY.day) else TODAY.year - 1
    out, prev = [None] * len(dates), None
    for i in range(len(dates) - 1, -1, -1):
        d = dates[i]
        if d is None:
            continue
        if prev and (d.month, d.day) > (prev.month, prev.day):
            year -= 1
        out[i] = d.replace(year=year)
        prev = d
    return out


def process(platform, path, posts, daily, report):
    rows = read_csv(path)
    if len(rows) < 2:
        report.append({"file": str(path.relative_to(ROOT)), "kind": "gol", "rows": 0})
        return
    h = map_headers(rows[0])
    body = rows[1:]
    g = lambda r, k: (r[h[k]] if k in h and h[k] < len(r) else "")
    order = slash_order([g(r, "date") for r in body[:300]])
    is_posts = any(k in h for k in ("id", "link", "caption"))
    rel = str(path.relative_to(ROOT))

    if not is_posts:
        if "date" not in h or "views" not in h:
            report.append({"file": rel, "kind": "necunoscut", "rows": 0,
                           "note": "Nu am găsit coloane de dată și vizualizări."})
            return
        dates = fill_years([parse_dt(g(r, "date"), order) for r in body])
        n = 0
        for r, d in zip(body, dates):
            if not d:
                continue
            key = d.date().isoformat()
            row = {"d": key, "v": num(g(r, "views")), "l": num(g(r, "likes")),
                   "c": num(g(r, "comments")), "sh": num(g(r, "shares"))}
            if key not in daily[platform] or row["v"] >= daily[platform][key]["v"]:
                daily[platform][key] = row
            n += 1
        report.append({"file": rel, "kind": "pe zi", "rows": n})
        return

    if "views" not in h:
        report.append({"file": rel, "kind": "necunoscut", "rows": 0, "note": "Lipsește coloana de vizualizări."})
        return
    n = 0
    for r in body:
        d = parse_dt(g(r, "date"), order)
        cap = re.sub(r"\s+", " ", g(r, "caption")).strip()
        link = g(r, "link").strip()
        p = {
            "p": platform,
            "a": g(r, "account").strip().lstrip("@") or "",
            "t": re.sub(r"^(ig|tt|tiktok)\s+", "", g(r, "type").strip(), flags=re.I).lower() or ("video" if platform == "tt" else ""),
            "d": d.isoformat(timespec="minutes") if d else "",
            "c": cap[:200] + ("…" if len(cap) > 200 else ""),
            "u": link if link.startswith("http") else "",
            "v": num(g(r, "views")), "r": num(g(r, "reach")), "l": num(g(r, "likes")),
            "cm": num(g(r, "comments")), "s": num(g(r, "saves")), "sh": num(g(r, "shares")),
            "f": num(g(r, "follows")),
        }
        if p["v"] <= 0:
            continue
        key = platform + "|" + (g(r, "id").strip() or p["u"] or f'{p["c"][:60]}|{p["d"]}')
        if key not in posts or p["v"] >= posts[key]["v"]:
            posts[key] = p
        n += 1
    missing = [k for k in ("likes", "comments", "saves", "shares") if k not in h]
    item = {"file": rel, "kind": "pe postare", "rows": n}
    if missing:
        item["note"] = "Lipsesc coloanele: " + ", ".join(missing) + " (socotite 0)."
    report.append(item)


def main():
    posts, daily, report = {}, {"ig": {}, "tt": {}}, []
    for platform, folder in (("ig", "instagram"), ("tt", "tiktok")):
        for path in sorted((ROOT / folder).glob("*")):
            if path.suffix.lower() in (".csv", ".tsv", ".txt"):
                process(platform, path, posts, daily, report)
            elif path.is_file() and path.name != ".gitkeep":
                report.append({"file": str(path.relative_to(ROOT)), "kind": "ignorat",
                               "rows": 0, "note": "Doar fișierele .csv sunt citite. Salvează-l ca CSV."})
    data = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "posts": sorted(posts.values(), key=lambda p: p["d"], reverse=True),
        "daily": {k: sorted(v.values(), key=lambda r: r["d"]) for k, v in daily.items()},
        "files": report,
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "data.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    shutil.copy(ROOT / "index.html", OUT / "index.html")
    for f in report:
        print(f'{f["file"]}: {f["kind"]}, {f["rows"]} rânduri {f.get("note", "")}')
    print(f'{len(data["posts"])} postări, {sum(len(v) for v in data["daily"].values())} zile -> site/data.json')


if __name__ == "__main__":
    sys.exit(main())
