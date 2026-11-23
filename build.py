#!/usr/bin/env python3
"""Сборка страницы журнала k8s-лаба.

  python build.py --validate   только проверка roadmap.yaml, journal/, review.yaml и runbook'ов
  python build.py              проверка + сборка site/ (главная, по странице на запись, план повторения)

Источник правды — roadmap.yaml (план и статусы), journal/<дата>.md (записи по дням)
и review.yaml (план повторения конспектов), runbooks/<slug>.md — runbook'и, на них ведут
ссылки runbook_url из алертов, situations/<slug>.md — что делать по симптому.
"""

import argparse
import datetime as dt
import html
import re
import sys
import urllib.parse
from pathlib import Path

import markdown
import yaml

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
STATUSES = {"done", "now", "todo"}
STATUS_LABEL = {"done": "сделано", "now": "сейчас", "todo": ""}
# Иконка вкладки плана повторения — очки на синем квадрате, инлайн, без отдельного файла
REVIEW_ICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
               '<rect width="64" height="64" rx="14" fill="#2f5fd0"/>'
               '<g fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round">'
               '<circle cx="19" cy="37" r="10"/><circle cx="45" cy="37" r="10"/>'
               '<path d="M29 35q3-4 6 0M9 34 5 24M55 34l4-10"/></g></svg>')


def load_roadmap() -> dict:
    return yaml.safe_load((ROOT / "roadmap.yaml").read_text(encoding="utf-8"))


def load_journal() -> list[dict]:
    entries = []
    for path in sorted((ROOT / "journal").glob("*.md"), reverse=True):
        text = path.read_text(encoding="utf-8")
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
        if not m:
            raise SystemExit(f"{path.name}: нет заголовка --- title/steps ---")
        meta = yaml.safe_load(m.group(1)) or {}
        entries.append({"date": path.stem, "title": meta.get("title", path.stem),
                        "steps": [str(s) for s in meta.get("steps", [])], "body": m.group(2)})
    return entries


def load_runbooks() -> list[dict]:
    """runbooks/<slug>.md — по алертам: заголовок --- title, alerts ---. Ссылка из алерта —
    runbooks/<slug>.html, поэтому slug меняется только вместе с runbook_url.
    situations/<slug>.md — по симптому, без алертов: checked — дата, когда прожили руками,
    journal — записи журнала с этой историей."""
    books = []
    for kind, folder in (("alert", "runbooks"), ("situation", "situations")):
        for path in sorted((ROOT / folder).glob("*.md")):
            text = path.read_text(encoding="utf-8")
            m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
            if not m:
                raise SystemExit(f"{folder}/{path.name}: нет заголовка --- title ---")
            meta = yaml.safe_load(m.group(1)) or {}
            books.append({"slug": path.stem, "title": meta.get("title", path.stem), "kind": kind,
                          "folder": folder, "alerts": [str(a) for a in meta.get("alerts", [])],
                          "checked": str(meta["checked"]) if meta.get("checked") else "",
                          "journal": [str(j) for j in meta.get("journal", [])], "body": m.group(2)})
    return books


def validate_runbooks(books: list[dict]) -> list[str]:
    errors, seen = [], {}
    for b in books:
        if not re.fullmatch(r"[a-z0-9-]+", b["slug"]):
            errors.append(f"{b['folder']}/{b['slug']}.md: имя файла — строчные буквы, цифры и дефис")
        if b["kind"] == "alert" and not b["alerts"]:
            errors.append(f"runbooks/{b['slug']}.md: пустой список alerts")
        if b["kind"] == "situation" and b["alerts"]:
            errors.append(f"situations/{b['slug']}.md: у ситуации нет alerts — это страница по симптому")
        for a in b["alerts"]:
            if a in seen:
                errors.append(f"алерт {a} описан и в {seen[a]}, и в {b['slug']}")
            seen[a] = b["slug"]
    return errors


def load_review() -> dict:
    return yaml.safe_load((ROOT / "review.yaml").read_text(encoding="utf-8"))


REVIEW_KEYS = ("start", "restart", "ladder", "private_url", "drill_url", "stages", "topics")
TOPIC_KEYS = ("id", "title", "area", "status", "brief", "steps", "read", "questions", "lab", "gdoc", "seen", "drill")
STAGE_KEYS = ("key", "title", "time", "when", "why", "steps")


def clean_streak(t: dict) -> int:
    """Сколько чистых повторов подряд в конце истории темы."""
    n = 0
    for r in sorted(t.get("repeats") or [], key=lambda r: str(r["date"]), reverse=True):
        if not r.get("clean"):
            break
        n += 1
    return n


def next_repeat(t: dict, ladder: list[int]) -> dt.date | None:
    """Лестница интервалов: после прохода ladder[0] дней, каждый чистый повтор подряд — ступенька
    выше (дальше последней не растёт), повтор с провалами — снова ladder[0]."""
    if t["status"] != "done":
        return None
    reps = sorted(t.get("repeats") or [], key=lambda r: str(r["date"]))
    last = dt.date.fromisoformat(str(reps[-1]["date"] if reps else t["done"]))
    return last + dt.timedelta(days=ladder[min(clean_streak(t), len(ladder) - 1)])


def fresh_steps(rv: dict, steps: dict) -> list[dict]:
    """Шаги лаба, закрытые с перестройки плана и ещё не закреплённые опросом."""
    since = dt.date.fromisoformat(str(rv["restart"]))
    done = {str(k) for k in (rv.get("consolidated") or {})}
    return [s for s in steps.values() if s["status"] == "done" and str(s["id"]) not in done
            and dt.date.fromisoformat(str(s["done"])) >= since]


def validate_review(rv: dict, rm: dict, books: list[dict]) -> list[str]:
    errors = [f"review.yaml: нет поля {k}" for k in REVIEW_KEYS if k not in rv]
    if errors:
        return errors
    steps = {str(s["id"]): s for b in rm["blocks"] for s in b["steps"]}
    pages = {f'{b["folder"]}/{b["slug"]}' for b in books}
    ids = [t.get("id") for t in rv["topics"]]
    if len(ids) != len(set(ids)):
        errors.append("review.yaml: повторяются id тем")
    mapped = set()
    for t in rv["topics"]:
        where = f"review.yaml, тема {t.get('id', '?')}"
        errors += [f"{where}: нет поля {k}" for k in TOPIC_KEYS if k not in t]
        if t.get("status") not in STATUSES:
            errors.append(f"{where}: status должен быть одним из {sorted(STATUSES)}")
        if t.get("status") == "done" and not t.get("done"):
            errors.append(f"{where}: пройдена, но нет даты done")
        for r in t.get("repeats") or []:
            if "date" not in r or "clean" not in r:
                errors.append(f"{where}: у повтора нужны date и clean")
        for sid in t.get("steps") or []:
            if str(sid) not in steps:
                errors.append(f"{where}: в roadmap.yaml нет шага {sid}")
            mapped.add(str(sid))
        focus = t.get("step_focus") or {}
        if (not isinstance(focus, dict) or set(focus) != set(t.get("steps") or [])
                or any(not isinstance(note, str) or not note.strip() for note in focus.values())):
            errors.append(f"{where}: у каждого связанного шага нужна подсказка в step_focus")
        for p in t.get("seen") or []:
            if p not in pages:
                errors.append(f"{where}: нет страницы {p}.md")
        for a in t.get("read") or []:
            if not (a.get("title") and a.get("note") and str(a.get("url", "")).startswith("https://")):
                errors.append(f"{where}: у статьи нужны title, note и url на https")
        for q in t.get("questions") or []:
            if not (q.get("q") and q.get("a")):
                errors.append(f"{where}: у вопроса нужны q и a")
        # Тему можно начинать, только когда она наполнена: todo может быть заготовкой
        if t.get("status") in ("now", "done") and (not t.get("brief") or len(t.get("questions") or []) < 3):
            errors.append(f"{where}: перед проходом нужны brief и хотя бы 3 вопроса")
        for key in ("practice", "practice_check"):
            if t.get("brief") and not (isinstance(t.get(key), str) and t[key].strip()):
                errors.append(f"{where}: наполненной теме нужно поле {key}")
    for sid, s in steps.items():
        if s["status"] == "done" and sid not in mapped:
            errors.append(f"review.yaml: шаг {sid} закрыт, но не входит ни в одну тему")
    for sid in rv.get("consolidated") or {}:
        if steps.get(str(sid), {}).get("status") != "done":
            errors.append(f"review.yaml, consolidated: шаг {sid} не закрыт в roadmap.yaml")
    if sum(1 for t in rv["topics"] if t.get("status") == "now") > 1:
        errors.append("review.yaml: «сейчас» больше одной темы")
    for sg in rv["stages"]:
        errors += [f"review.yaml, режим {sg.get('key', '?')}: нет поля {k}" for k in STAGE_KEYS if k not in sg]
        if not sg.get("steps") or any(not (s.get("name") and s.get("how")) for s in sg["steps"]):
            errors.append(f"review.yaml, режим {sg.get('key', '?')}: у каждого подшага нужны name и how")
    stage_ids = [sg.get("key") for sg in rv["stages"]]
    if len(stage_ids) != len(set(stage_ids)) or not {"pass", "fresh", "repeat", "daily", "interview"} <= set(stage_ids):
        errors.append("review.yaml: нужны пять режимов с уникальными ключами: pass, fresh, repeat, daily, interview")
    return errors


def validate(rm: dict, journal: list[dict]) -> list[str]:
    errors = []
    ids = []
    for b in rm.get("blocks", []):
        for key in ("id", "num", "title", "days", "target", "why", "steps"):
            if key not in b:
                errors.append(f"блок {b.get('id', '?')}: нет поля {key}")
        for s in b.get("steps", []):
            sid = str(s.get("id"))
            ids.append(sid)
            if s.get("status") not in STATUSES:
                errors.append(f"шаг {sid}: status должен быть одним из {sorted(STATUSES)}")
            if s.get("status") == "done" and not s.get("done"):
                errors.append(f"шаг {sid}: сделан, но нет даты done")
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        errors.append(f"повторяются id шагов: {sorted(dup)}")
    now = [i for b in rm["blocks"] for s in b["steps"] if s["status"] == "now" for i in [str(s["id"])]]
    if len(now) > 1:
        errors.append(f"«сейчас» больше одного шага: {now}")
    for sid in rm.get("today", {}).get("steps", []):
        if str(sid) not in ids:
            errors.append(f"today: нет такого шага {sid}")
    dates = {e["date"] for e in journal}
    for b in rm["blocks"]:
        for s in b["steps"]:
            if s.get("journal") and str(s["journal"]) not in dates:
                errors.append(f"шаг {s['id']}: нет записи journal/{s['journal']}.md")
    for e in journal:
        try:
            dt.date.fromisoformat(e["date"])
        except ValueError:
            errors.append(f"journal/{e['date']}.md: имя файла должно быть датой YYYY-MM-DD")
        for sid in e["steps"]:
            if sid not in ids:
                errors.append(f"journal/{e['date']}.md: нет такого шага {sid}")
    return errors


def esc(s) -> str:
    return html.escape(str(s or ""))


def ddmm(iso: str) -> str:
    d = dt.date.fromisoformat(str(iso))
    return f"{d.day:02d}.{d.month:02d}"


def page(title: str, body: str, prefix: str = "", icon: str = "") -> str:
    tpl = (ROOT / "web" / "page.html").read_text(encoding="utf-8")
    link = f'<link rel="icon" href="data:image/svg+xml,{urllib.parse.quote(icon)}">\n' if icon else ""
    return (tpl.replace("{{TITLE}}", esc(title)).replace("{{ICON}}", link)
            .replace("{{PREFIX}}", prefix).replace("{{BODY}}", body))


def step_row(s: dict, prefix: str) -> str:
    st = s["status"]
    pill = ""
    if st == "now":
        pill = '<span class="pill now">сейчас</span>'
    elif st == "done":
        pill = f'<span class="pill done">сделано {ddmm(s["done"])}</span>'
    link = ""
    if s.get("journal"):
        link = f' <a class="jlink" href="{prefix}journal/{s["journal"]}.html">журнал →</a>'
    note = f'<div class="note">{esc(s.get("note"))}</div>' if s.get("note") else ""
    hours = f'~{s["hours"]} ч' if s.get("hours") else ""
    mark = {"done": "✓", "now": "▸", "todo": ""}[st]
    return (f'<li class="step {st}"><span class="mark" aria-hidden="true">{mark}</span>'
            f'<span class="num">{esc(s["id"])}</span>'
            f'<div class="title"><span class="t">{esc(s["title"])}</span>{pill}{link}{note}</div>'
            f'<span class="h">{hours}</span></li>')


def build_index(rm: dict, journal: list[dict]) -> str:
    steps = {str(s["id"]): s for b in rm["blocks"] for s in b["steps"]}
    all_steps = list(steps.values())
    done = sum(1 for s in all_steps if s["status"] == "done")
    core_left = sum(s.get("hours", 0) for b in rm["blocks"] if b["id"] != "b7"
                    for s in b["steps"] if s["status"] != "done")
    trial_end = dt.date.fromisoformat(str(rm["trial_end"]))
    days_left = max(0, (trial_end - dt.date.today()).days)
    pct = round(done / len(all_steps) * 100) if all_steps else 0

    today = rm.get("today", {})
    today_steps = "".join(step_row(steps[str(i)], "") for i in today.get("steps", []))
    out = [f'''
<header class="top">
  <div class="head-row"><h1>Маршрут k8s-лаба</h1>
    <div class="label">kubeadm на голых VM · GCP · триал до {trial_end:%d.%m.%Y}</div></div>
  <p class="lead">Production-like Kubernetes руками, без managed: kubeadm, Cilium, ArgoCD, Prometheus.
  Кластер поднят — теперь его эксплуатирую: сломать, заметить по алерту, починить по runbook, записать.</p>
  <div class="stats">
    <div><span class="muted">шагов пройдено</span> <b>{done} из {len(all_steps)}</b></div>
    <div><span class="muted">часов впереди</span> <b>~{core_left}</b> <span class="muted">в блоках 1–6</span></div>
    <div><span class="muted">до конца триала</span> <b id="days" data-end="{trial_end.isoformat()}">{days_left} дн.</b></div>
  </div>
  <div class="bar" aria-hidden="true"><i style="width:{pct}%"></i></div>
</header>
<section class="today" aria-labelledby="today-h">
  <div class="label" id="today-h">Сегодня · {ddmm(today["date"])}</div>
  <div class="focus">{esc(today.get("focus"))}</div>
  <ul class="steps">{today_steps}</ul>
  <div class="note">{esc(today.get("note"))}</div>
</section>
<p class="review-link"><a href="review.html">План повторения конспектов →</a></p>''']

    if journal:
        items = "".join(
            f'<li><span class="date mono">{ddmm(e["date"])}</span> '
            f'<a href="journal/{e["date"]}.html">{esc(e["title"])}</a></li>' for e in journal[:7])
        out.append(f'<section class="journal-list" aria-labelledby="j-h"><h2 id="j-h">Журнал</h2><ul>{items}</ul></section>')

    out.append('<div class="blocks">')
    for b in rm["blocks"]:
        bs = b["steps"]
        bd = sum(1 for s in bs if s["status"] == "done")
        bpct = round(bd / len(bs) * 100) if bs else 0
        done_when = f'<div class="done-when"><b>Готово, когда:</b> {esc(b["done_when"])}</div>' if b.get("done_when") and b["done_when"] != "—" else ""
        rows = "".join(step_row(s, "") for s in bs)
        out.append(f'''
<section class="block" id="{esc(b["id"])}" aria-labelledby="h-{esc(b["id"])}">
  <div class="block-head"><span class="block-num mono">{esc(b.get("num", ""))}</span>
    <h2 id="h-{esc(b["id"])}">{esc(b["title"])}</h2>
    <span class="block-meta mono">{bd}/{len(bs)} · {esc(b["days"])} · {esc(b["target"])}</span>
    <div class="why">{esc(b["why"])}</div>{done_when}</div>
  <div class="bar" aria-hidden="true"><i style="width:{bpct}%"></i></div>
  <ul class="steps">{rows}</ul>
</section>''')
    out.append('</div>')
    out.append(f'<footer>Собрано из <span class="mono">roadmap.yaml</span> и <span class="mono">journal/</span> · '
               f'{dt.datetime.now(dt.timezone.utc):%d.%m.%Y %H:%M} UTC · '
               '<a href="https://github.com/Tsim0710/k8s-lab-journal">исходники</a> · '
               '<a href="https://tsim0710.github.io/devops-anki/">карточки devops-anki</a> · '
               '<a href="review.html">план повторения</a> · '
               '<a href="runbooks/index.html">runbook\'и</a> · '
               '<a href="situations/index.html">ситуации</a></footer>')
    return page("Маршрут k8s-лаба", "\n".join(out))


def build_entry(e: dict, rm: dict) -> str:
    steps = {str(s["id"]): s for b in rm["blocks"] for s in b["steps"]}
    md = markdown.markdown(e["body"], extensions=["tables", "fenced_code", "sane_lists"])
    chips = "".join(f'<span class="chip mono">{esc(sid)} {esc(steps[sid]["title"])}</span>' for sid in e["steps"])
    body = f'''
<nav class="back"><a href="../index.html">← маршрут</a></nav>
<article class="entry">
  <div class="label">{dt.date.fromisoformat(e["date"]):%d.%m.%Y}</div>
  <h1>{esc(e["title"])}</h1>
  <div class="chips">{chips}</div>
  <div class="md">{md}</div>
</article>'''
    return page(e["title"], body, "../")


def build_runbook(b: dict) -> str:
    md = markdown.markdown(b["body"], extensions=["tables", "fenced_code", "sane_lists"])
    if b["kind"] == "situation":
        checked = f"проверено руками {ddmm(b['checked'])}" if b["checked"] else "не проверено руками"
        chips = f'<span class="chip">{checked}</span>' + "".join(
            f'<a class="chip mono" href="../journal/{esc(j)}.html">журнал {ddmm(j)}</a>' for j in b["journal"])
    else:
        chips = "".join(f'<span class="chip mono">{esc(a)}</span>' for a in b["alerts"])
    body = f'''
<nav class="back"><a href="index.html">← {"все ситуации" if b["kind"] == "situation" else "все runbook'и"}</a></nav>
<article class="entry">
  <div class="label">{"ситуация" if b["kind"] == "situation" else "runbook"}</div>
  <h1>{esc(b["title"])}</h1>
  <div class="chips">{chips}</div>
  <div class="md">{md}</div>
</article>'''
    return page(b["title"], body, "../")


def build_runbooks_index(books: list[dict]) -> str:
    rows = "".join(
        f'<li><a href="{esc(b["slug"])}.html">{esc(b["title"])}</a>'
        f'<div class="note mono">{esc(", ".join(b["alerts"]))}</div></li>' for b in books if b["kind"] == "alert")
    body = f'''
<nav class="back"><a href="../index.html">← маршрут</a></nav>
<article class="entry">
  <div class="label">runbook'и</div>
  <h1>Что делать, когда пришёл алерт</h1>
  <p>Сюда ведут ссылки runbook из сообщений в Telegram. Под каждым заголовком — алерты, которые
  ведут на эту страницу. Алерта нет в списке — начинай с «Порядка разбора». Случилось что-то, а
  алерта нет — <a href="../situations/index.html">ситуации</a>.</p>
  <ul class="runbooks">{rows}</ul>
</article>'''
    return page("Runbook'и", body, "../")


def build_situations_index(books: list[dict]) -> str:
    rows = "".join(
        f'<li><a href="{esc(b["slug"])}.html">{esc(b["title"])}</a>'
        f'<div class="note">{"проверено руками " + ddmm(b["checked"]) if b["checked"] else "не проверено руками"}</div></li>'
        for b in books if b["kind"] == "situation")
    body = f'''
<nav class="back"><a href="../index.html">← маршрут</a></nav>
<article class="entry">
  <div class="label">ситуации</div>
  <h1>Что делать, если сломалось, а алерта нет</h1>
  <p>Страницы по симптому. «Проверено руками» — прожито в лабе, дата ведёт в журнал. Пришёл алерт —
  ссылка в сообщении ведёт в <a href="../runbooks/index.html">runbook'и</a>.</p>
  <ul class="runbooks">{rows}</ul>
</article>'''
    return page("Ситуации", body, "../")


LAB_DOC = re.compile(r"^((?:\d\d-[a-z0-9-]+)|(?:interview/[a-z0-9-]+))(.*)$", re.S)
LOCK = '<span class="lock" title="приватное репо: откроется, если вошёл в GitHub как Tsim0710">🔒</span>'

# Сроки повторов сверяются с датой в браузере, а не со временем сборки.
# Галочки шагов текущей темы — только удобство, живут в localStorage этого браузера.
REVIEW_JS = """
(function () {
  var today = new Date(); today.setHours(0, 0, 0, 0);
  var due = document.getElementById("due"), n = 0;
  document.querySelectorAll("[data-next]").forEach(function (el) {
    var d = new Date(el.dataset.next + "T00:00:00");
    if (d > today) return;
    var topic = el.closest("details.topic"); topic.classList.add("due");
    el.classList.add(d < today ? "late" : "on");
    var item = document.createElement("li"), a = document.createElement("a");
    a.href = "#" + topic.id;
    a.textContent = topic.querySelector(".num").textContent + " · " + topic.dataset.title;
    item.appendChild(a);
    if (d < today) item.appendChild(document.createTextNode(
      " — просрочено с " + el.dataset.next.slice(8, 10) + "." + el.dataset.next.slice(5, 7)));
    due.appendChild(item); n++;
  });
  if (n) document.querySelector(".due-box").hidden = false;
  // ссылка на тему (#t-N) раскрывает её
  function openHash() {
    var t = document.getElementById(location.hash.slice(1));
    if (t && t.tagName === "DETAILS") t.open = true;
  }
  window.addEventListener("hashchange", openHash); openHash();
  document.querySelectorAll("input[data-key]").forEach(function (cb) {
    try { cb.checked = localStorage.getItem(cb.dataset.key) === "1"; } catch (e) {}
    cb.addEventListener("change", function () {
      try { localStorage.setItem(cb.dataset.key, cb.checked ? "1" : "0"); } catch (e) {}
    });
  });
})();
"""


def inline(s) -> str:
    """Экранирование плюс `код` и **жирный** — для текстов из review.yaml."""
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", esc(s))
    return re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", out)


def lab_ref(rv: dict, item: str) -> str:
    """«03-observability — разделы …» → ссылка на приватный конспект, остальное — текстом."""
    m = LAB_DOC.match(item)
    if not m:
        return inline(item)
    return (f'<a class="mono" href="{esc(rv["private_url"])}{esc(m.group(1))}.md">{esc(m.group(1))}</a>'
            f'{LOCK}{inline(m.group(2))}')


def src_row(key: str, items: list[str]) -> str:
    if not items:
        return ""
    rows = "".join(f"<li>{item}</li>" for item in items)
    return f'<div class="src"><span class="src-k">{key}</span><ul>{rows}</ul></div>'


def tm(x: dict) -> str:
    return f' <span class="tm">{esc(x["time"])}</span>' if x.get("time") else ""


def step_item(sid: str, steps: dict, rv: dict, focus: str, topic_id: int | None = None) -> str:
    s = steps[sid]
    note = f'<div class="note">{inline(focus)}</div>'
    if s["status"] != "done":
        return (f'<li class="ahead"><span class="mono">{esc(sid)}</span> {esc(s["title"])} '
                f'<span class="muted">— впереди в лабе</span>{note}</li>')
    links = [f'<a href="journal/{esc(s["journal"])}.html">журнал</a>'] if s.get("journal") else []
    links.append(f'<a href="{esc(rv["private_url"])}steps/{esc(sid)}.md">итог шага</a>{LOCK}')
    if topic_id is not None:
        links.append(f'<a href="#t-{esc(topic_id)}">тема {esc(topic_id)}</a>')
    return (f'<li><span class="mono">{esc(sid)}</span> {esc(s["title"])} '
            f'<span class="links">{" · ".join(links)}</span>{note}</li>')


def topic_block(t: dict, rv: dict, steps: dict, titles: dict) -> str:
    st = t["status"]
    nxt = next_repeat(t, rv["ladder"])
    pill = ""
    if st == "now":
        pill = '<span class="pill now">сейчас</span>'
    elif st == "done":
        pill = f'<span class="pill done">пройдено {ddmm(t["done"])}</span>'
        if t.get("repeats"):
            pill += f'<span class="pill rep">повторов: {len(t["repeats"])}</span>'
    when = (f'<span class="h next" data-next="{nxt.isoformat()}">повтор {ddmm(nxt.isoformat())}</span>'
            if nxt else '<span class="h"></span>')
    mark = {"done": "✓", "now": "▸", "todo": ""}[st]

    parts = [f'<div class="tsec"><h3>Простыми словами</h3><p class="brief">{inline(t["brief"])}</p></div>' if t.get("brief")
             else '<p class="brief muted">Тема ещё не наполнена.</p>']
    if t.get("weak"):
        parts.append(f'<div class="weak"><span class="src-k">Провисло</span><span>{inline("; ".join(t["weak"]))}</span></div>')
    if t.get("practice"):
        parts.append(f'<div class="tsec"><h3>Упражнение</h3><p>{inline(t["practice"])}</p>'
                     f'<div class="qa"><details><summary>Сверить свой ответ</summary>'
                     f'<div class="ans">{inline(t["practice_check"])}</div></details></div></div>')
    if t.get("questions"):
        qa = "".join(f'<details><summary>{inline(q["q"])}</summary><div class="ans">{inline(q["a"])}</div></details>'
                     for q in t["questions"])
        parts.append(f'<div class="tsec"><h3>Проверь себя · {len(t["questions"])}</h3><div class="qa">{qa}</div></div>')
    if t.get("read"):
        reads = "".join(
            f'<li><a href="{esc(a["url"])}">{esc(a["title"])}</a>'
            f'<span class="meta">{esc(a.get("lang", "en"))}{" · ~" + str(a["min"]) + " мин" if a.get("min") else ""}</span>'
            f'<div class="note">{inline(a["note"])}</div></li>' for a in t["read"])
        parts.append(f'<div class="tsec"><h3>Основа</h3><ul class="reads">{reads}</ul></div>')
    if t.get("steps"):
        items = "".join(step_item(str(sid), steps, rv, t["step_focus"][sid]) for sid in t["steps"])
        parts.append(f'<div class="tsec"><h3>Шаги лаба</h3><ul class="lsteps">{items}</ul></div>')
    seen = t.get("seen") or []
    srcs = (src_row("Ситуации", [f'<a href="{esc(p)}.html">{esc(titles[p])}</a>' for p in seen if p.startswith("situations/")])
            + src_row("Runbook'и", [f'<a href="{esc(p)}.html">{esc(titles[p])}</a>' for p in seen if p.startswith("runbooks/")])
            + src_row("Конспекты", [lab_ref(rv, x) for x in t.get("lab") or []])
            + src_row("Google-конспекты", [inline(x) for x in t.get("gdoc") or []])
            + src_row("Тренажёр", [inline(x) for x in t.get("drill") or []]))
    if srcs:
        parts.append(f'<div class="tsec srcs">{srcs}</div>')
    return (f'<details class="topic {st}" id="t-{esc(t["id"])}" data-title="{esc(t["title"])}"{" open" if st == "now" else ""}>'
            f'<summary><span class="mark" aria-hidden="true">{mark}</span><span class="num">{esc(t["id"])}</span>'
            f'<span class="title"><span class="t">{esc(t["title"])}</span><span class="area">{esc(t["area"])}</span>{pill}</span>'
            f'{when}</summary><div class="tbody">{"".join(parts)}</div></details>')


def stage_block(sg: dict) -> str:
    items = "".join(f'<li><b>{esc(x["name"])}</b>{tm(x)}<div class="howto">{inline(x["how"])}</div></li>'
                    for x in sg["steps"])
    return (f'<details class="stage" id="m-{esc(sg["key"])}"><summary><span class="st">{esc(sg["title"])}</span>'
            f'<span class="tm">{esc(sg["time"])}</span></summary>'
            f'<div class="stage-body"><div class="stage-when">{inline(sg["when"])}</div>'
            f'<p class="muted">{inline(sg["why"])}</p><ol>{items}</ol></div></details>')


def build_review(rv: dict, rm: dict, books: list[dict]) -> str:
    topics = rv["topics"]
    steps = {str(s["id"]): s for b in rm["blocks"] for s in b["steps"]}
    titles = {f'{b["folder"]}/{b["slug"]}': b["title"] for b in books}
    stages = {sg["key"]: sg for sg in rv["stages"]}
    topic_of = {}
    for t in topics:
        for sid in t["steps"]:
            topic_of.setdefault(str(sid), t)
    done = sum(1 for t in topics if t["status"] == "done")
    reps = sum(len(t.get("repeats") or []) for t in topics)
    pct = round(done / len(topics) * 100) if topics else 0
    fresh = fresh_steps(rv, steps)

    cur = next((t for t in topics if t["status"] == "now"), None)
    if cur:
        p = stages["pass"]
        checklist = "".join(
            f'<li><label><input type="checkbox" data-key="rv2-{esc(cur["id"])}-{i}"> <b>{esc(x["name"])}</b></label>{tm(x)}'
            f'<div class="howto">{inline(x["how"])}</div></li>' for i, x in enumerate(p["steps"]))
        cur_html = (f'<div class="focus"><a href="#t-{esc(cur["id"])}">Тема {esc(cur["id"])} · {esc(cur["title"])}</a></div>'
                    f'<div class="muted"><a href="#m-pass">{esc(p["title"])}</a> · {esc(p["time"])}</div>'
                    f'<ol class="checklist">{checklist}</ol>')
    else:
        cur_html = '<div class="focus">Первый проход закончен — дальше только повторы</div>'
    fresh_html = ""
    if fresh:
        items = "".join(
            step_item(str(s["id"]), steps, rv, topic_of[str(s["id"])]["step_focus"][s["id"]],
                      topic_of[str(s["id"])]["id"])
            for s in fresh)
        fresh_html = (f'<div class="fresh-box"><div class="label"><a href="#m-fresh">Свежие шаги лаба</a> — '
                      f'закрепить на опросе</div><ul>{items}</ul></div>')
    daily = stages["daily"]

    body = f'''
<nav class="back"><a href="index.html">← маршрут</a></nav>
<header class="top">
  <div class="head-row"><h1>План повторения</h1>
    <div class="label">шаги лаба · статьи · конспекты · devops-anki</div></div>
  <p class="lead">На первый проход бери одну тему. Ответь по памяти, сверься с источником и разберись
  с одним результатом из лаба. В «Сегодня» появятся темы по сроку и шаги для опроса.
  M1–M25 — номера вкладок Google-конспекта Kubernetes. Прямые ссылки и привязки к материалам лаба
  собраны в <a href="{esc(rv['private_url'])}interview/review-plan.md#указатель-модулей-kubernetes">приватном указателе</a>{LOCK}.</p>
  <div class="stats">
    <div><span class="muted">тем пройдено</span> <b>{done} из {len(topics)}</b></div>
    <div><span class="muted">повторов</span> <b>{reps}</b></div>
    <div><span class="muted">свежих шагов ждут опроса</span> <b>{len(fresh)}</b></div>
    <div><span class="muted">начало</span> <b>{ddmm(rv["start"])}</b></div>
  </div>
  <div class="bar" aria-hidden="true"><i style="width:{pct}%"></i></div>
</header>
<section class="today" aria-labelledby="rt-h">
  <div class="label" id="rt-h">Сегодня</div>
  <div class="due-box" hidden><div class="label"><a href="#m-repeat">Повторить по сроку</a></div><ul id="due"></ul></div>{fresh_html}
  {cur_html}
  <p class="note">Галочки сохраняются в этом браузере. Пройденные темы и повторы фиксируются после твоего отчёта.</p>
  <div class="note"><a href="#m-daily">{esc(daily["title"])}</a>, {esc(daily["time"])}: {inline(daily["steps"][0]["how"])}</div>
</section>
<section class="block" aria-labelledby="rs-h">
  <div class="block-head"><span class="block-num mono">{len(rv["stages"])}</span><h2 id="rs-h">Как повторять</h2>
    <span class="block-meta mono">режимы</span>
    <div class="why">Нажми на режим — внутри по шагам: что делать, сколько времени и зачем.</div></div>
  <div class="stages">{"".join(stage_block(sg) for sg in rv["stages"])}</div>
</section>
<section class="block" aria-labelledby="rl-h">
  <div class="block-head"><span class="block-num mono">{len(topics)}</span><h2 id="rl-h">Темы</h2>
    <span class="block-meta mono">{done}/{len(topics)}</span>
    <div class="why">В порядке первого прохода. Нажми на тему — внутри всё для неё. {LOCK} — приватные конспекты
    лаба: откроются, если вошёл в GitHub как Tsim0710.</div></div>
  <div class="topics">{"".join(topic_block(t, rv, steps, titles) for t in topics)}</div>
</section>
<footer>Собрано из <span class="mono">review.yaml</span> и <span class="mono">roadmap.yaml</span> ·
{dt.datetime.now(dt.timezone.utc):%d.%m.%Y %H:%M} UTC ·
<a href="https://github.com/Tsim0710/k8s-lab-journal/blob/main/AGENTS.md#план-повторения">как вести план</a> ·
подробно с источниками — <a href="{esc(rv["private_url"])}interview/review-plan.md">review-plan.md</a>{LOCK}</footer>
<script>{REVIEW_JS}</script>'''
    return page("План повторения", body, icon=REVIEW_ICON)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args()
    rm, journal, rv, books = load_roadmap(), load_journal(), load_review(), load_runbooks()
    errors = validate(rm, journal) + validate_review(rv, rm, books) + validate_runbooks(books)
    if errors:
        print("\n".join("  ✗ " + e for e in errors))
        return 1
    n = sum(len(b["steps"]) for b in rm["blocks"])
    print(f"ok: {len(rm['blocks'])} блоков, {n} шагов, {len(journal)} записей журнала, "
          f"{len(rv['topics'])} тем повторения, {sum(b['kind'] == 'alert' for b in books)} runbook'ов, "
          f"{sum(b['kind'] == 'situation' for b in books)} ситуаций")
    if args.validate:
        return 0
    (SITE / "journal").mkdir(parents=True, exist_ok=True)
    (SITE / "index.html").write_text(build_index(rm, journal), encoding="utf-8")
    for e in journal:
        (SITE / "journal" / f"{e['date']}.html").write_text(build_entry(e, rm), encoding="utf-8")
    (SITE / "review.html").write_text(build_review(rv, rm, books), encoding="utf-8")
    for folder in ("runbooks", "situations"):
        (SITE / folder).mkdir(parents=True, exist_ok=True)
    (SITE / "runbooks" / "index.html").write_text(build_runbooks_index(books), encoding="utf-8")
    (SITE / "situations" / "index.html").write_text(build_situations_index(books), encoding="utf-8")
    for b in books:
        (SITE / b["folder"] / f"{b['slug']}.html").write_text(build_runbook(b), encoding="utf-8")
    (SITE / ".nojekyll").write_text("")
    print(f"собрано: site/index.html + {len(journal)} страниц журнала + site/review.html + runbooks/ + situations/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
