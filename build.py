#!/usr/bin/env python3
"""Сборка страницы журнала k8s-лаба.

  python build.py --validate   только проверка roadmap.yaml, journal/ и review.yaml
  python build.py              проверка + сборка site/ (главная, по странице на запись, план повторения)

Источник правды — roadmap.yaml (план и статусы), journal/<дата>.md (записи по дням)
и review.yaml (план повторения конспектов).
"""

import argparse
import datetime as dt
import html
import re
import sys
from pathlib import Path

import markdown
import yaml

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
STATUSES = {"done", "now", "todo"}
STATUS_LABEL = {"done": "сделано", "now": "сейчас", "todo": ""}


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


def load_review() -> dict:
    return yaml.safe_load((ROOT / "review.yaml").read_text(encoding="utf-8"))


def next_repeat(t: dict) -> dt.date | None:
    """После первого прохода +7 дней, после чистого повтора +21, после повтора с провалами +7."""
    if t["status"] != "done":
        return None
    reps = sorted(t.get("repeats") or [], key=lambda r: str(r["date"]))
    last = dt.date.fromisoformat(str(reps[-1]["date"] if reps else t["done"]))
    return last + dt.timedelta(days=21 if reps and reps[-1].get("clean") else 7)


def validate_review(rv: dict) -> list[str]:
    errors = []
    ids = [t.get("id") for t in rv.get("topics", [])]
    if len(ids) != len(set(ids)):
        errors.append("review.yaml: повторяются id тем")
    for t in rv.get("topics", []):
        tid = t.get("id", "?")
        for key in ("id", "title", "gdoc", "lab", "drill", "status"):
            if key not in t:
                errors.append(f"review.yaml, тема {tid}: нет поля {key}")
        if t.get("status") not in STATUSES:
            errors.append(f"review.yaml, тема {tid}: status должен быть одним из {sorted(STATUSES)}")
        if t.get("status") == "done" and not t.get("done"):
            errors.append(f"review.yaml, тема {tid}: пройдена, но нет даты done")
        for r in t.get("repeats") or []:
            if "date" not in r or "clean" not in r:
                errors.append(f"review.yaml, тема {tid}: у повтора нужны date и clean")
    if sum(1 for t in rv.get("topics", []) if t.get("status") == "now") > 1:
        errors.append("review.yaml: «сейчас» больше одной темы")
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


def page(title: str, body: str, prefix: str = "") -> str:
    tpl = (ROOT / "web" / "page.html").read_text(encoding="utf-8")
    return tpl.replace("{{TITLE}}", esc(title)).replace("{{PREFIX}}", prefix).replace("{{BODY}}", body)


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
               '<a href="review.html">план повторения</a></footer>')
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


def src_rows(t: dict) -> str:
    rows = [("Google Doc", t["gdoc"]), ("Лаб", t["lab"]), ("Тренажёр", t["drill"])]
    return "".join(f'<div class="src"><span class="src-k">{k}</span><span>{esc(" · ".join(v))}</span></div>'
                   for k, v in rows if v)


def topic_row(t: dict) -> str:
    st = t["status"]
    nxt = next_repeat(t)
    pill = ""
    if st == "now":
        pill = '<span class="pill now">сейчас</span>'
    elif st == "done":
        reps = t.get("repeats") or []
        pill = f'<span class="pill done">пройдено {ddmm(t["done"])}</span>'
        if reps:
            pill += f'<span class="pill rep">повторов: {len(reps)}</span>'
    why = f' <span class="muted">— {esc(t["why"])}</span>' if t.get("why") else ""
    weak = ""
    if t.get("weak"):
        weak = '<div class="weak"><span class="src-k">Провисло</span><span>' + esc("; ".join(t["weak"])) + "</span></div>"
    when = f'<span class="h next" data-next="{nxt.isoformat()}">повтор {ddmm(nxt.isoformat())}</span>' if nxt else '<span class="h"></span>'
    mark = {"done": "✓", "now": "▸", "todo": ""}[st]
    return (f'<li class="step {st}" data-title="{esc(t["title"])}"><span class="mark" aria-hidden="true">{mark}</span>'
            f'<span class="num">{esc(t["id"])}</span>'
            f'<div class="title"><span class="t">{esc(t["title"])}</span>{why}{pill}{src_rows(t)}{weak}</div>'
            f'{when}</li>')


def build_review(rv: dict) -> str:
    topics = rv["topics"]
    done = sum(1 for t in topics if t["status"] == "done")
    reps = sum(len(t.get("repeats") or []) for t in topics)
    pct = round(done / len(topics) * 100) if topics else 0
    cur = next((t for t in topics if t["status"] == "now"), None)
    steps = "".join(f'<li><label><input type="checkbox" data-key="review-{esc(cur["id"]) if cur else 0}-{i}"> {esc(m)}</label></li>'
                    for i, m in enumerate(rv["method"]))
    cur_html = ""
    if cur:
        cur_html = f'''
  <div class="focus">Тема {esc(cur["id"])} · {esc(cur["title"])}</div>
  {src_rows(cur)}
  <ol class="checklist">{steps}</ol>'''
    else:
        cur_html = '<div class="focus">Первый проход закончен — дальше только повторы</div>'
    rows = "".join(topic_row(t) for t in topics)
    prep = "".join(f"<li>{esc(x)}</li>" for x in rv["before_interview"])
    body = f'''
<nav class="back"><a href="index.html">← маршрут</a></nav>
<header class="top">
  <div class="head-row"><h1>План повторения</h1>
    <div class="label">Google-конспекты · конспекты лаба · devops-anki</div></div>
  <p class="lead">Первый проход — одна тема в день, около 70 минут, утром до лаба. Каждая тема собрана из трёх
  источников: теория в Google-конспекте, то же самое руками в лабе, проверка в
  <a href="{esc(rv["drill_url"])}">тренажёре</a>. Повторы приходят сами: через неделю, потом через три.</p>
  <div class="stats">
    <div><span class="muted">тем пройдено</span> <b>{done} из {len(topics)}</b></div>
    <div><span class="muted">повторов сделано</span> <b>{reps}</b></div>
    <div><span class="muted">начало</span> <b>{ddmm(rv["start"])}</b></div>
  </div>
  <div class="bar" aria-hidden="true"><i style="width:{pct}%"></i></div>
</header>
<section class="today" aria-labelledby="rt-h">
  <div class="label" id="rt-h">Сегодня</div>{cur_html}
  <div class="due-box" hidden><div class="label">Повторить сегодня</div><ul id="due"></ul></div>
  <div class="note">{esc(rv["daily"])}</div>
</section>
<section class="block" aria-labelledby="rl-h">
  <div class="block-head"><span class="block-num mono">15</span><h2 id="rl-h">Темы</h2>
    <span class="block-meta mono">{done}/{len(topics)}</span></div>
  <ul class="steps">{rows}</ul>
</section>
<section class="block" aria-labelledby="ri-h">
  <h2 id="ri-h">Перед собесом, за 1–2 дня</h2>
  <ol class="plain">{prep}</ol>
</section>
<footer>Собрано из <span class="mono">review.yaml</span> · {dt.datetime.now(dt.timezone.utc):%d.%m.%Y %H:%M} UTC ·
план с объяснением порядка — <span class="mono">k8s-lab-infra/docs/interview/review-plan.md</span></footer>
<script>
// Сроки повторов сверяются с датой в браузере, а не со временем сборки.
// Галочки шагов текущей темы — только удобство, живут в localStorage этого браузера.
(function () {{
  var today = new Date(); today.setHours(0, 0, 0, 0);
  var due = document.getElementById("due"), n = 0;
  document.querySelectorAll("[data-next]").forEach(function (el) {{
    var d = new Date(el.dataset.next + "T00:00:00");
    if (d > today) return;
    var li = el.closest("li.step"); li.classList.add("due");
    el.classList.add(d < today ? "late" : "on");
    var item = document.createElement("li");
    item.textContent = li.querySelector(".num").textContent + " · " + li.dataset.title + (d < today ? " — просрочено" : "");
    due.appendChild(item); n++;
  }});
  if (n) document.querySelector(".due-box").hidden = false;
  document.querySelectorAll("input[data-key]").forEach(function (cb) {{
    try {{ cb.checked = localStorage.getItem(cb.dataset.key) === "1"; }} catch (e) {{}}
    cb.addEventListener("change", function () {{
      try {{ localStorage.setItem(cb.dataset.key, cb.checked ? "1" : "0"); }} catch (e) {{}}
    }});
  }});
}})();
</script>'''
    return page("План повторения", body)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--validate", action="store_true")
    args = ap.parse_args()
    rm, journal, rv = load_roadmap(), load_journal(), load_review()
    errors = validate(rm, journal) + validate_review(rv)
    if errors:
        print("\n".join("  ✗ " + e for e in errors))
        return 1
    n = sum(len(b["steps"]) for b in rm["blocks"])
    print(f"ok: {len(rm['blocks'])} блоков, {n} шагов, {len(journal)} записей журнала, {len(rv['topics'])} тем повторения")
    if args.validate:
        return 0
    (SITE / "journal").mkdir(parents=True, exist_ok=True)
    (SITE / "index.html").write_text(build_index(rm, journal), encoding="utf-8")
    for e in journal:
        (SITE / "journal" / f"{e['date']}.html").write_text(build_entry(e, rm), encoding="utf-8")
    (SITE / "review.html").write_text(build_review(rv), encoding="utf-8")
    (SITE / ".nojekyll").write_text("")
    print(f"собрано: site/index.html + {len(journal)} страниц журнала + site/review.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
