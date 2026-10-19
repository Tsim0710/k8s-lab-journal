# k8s-lab-journal

Журнал и маршрут пет-проекта: production-like Kubernetes руками — kubeadm на голых
VM в GCP, Cilium, ArgoCD, Prometheus, Loki. Кластер поднят, теперь его эксплуатирую:
сломать, заметить по алерту, починить по runbook, записать.

**Страница: https://tsim0710.github.io/k8s-lab-journal/** — что сегодня, где я
в маршруте, записи по дням.

| Что | Где |
|---|---|
| План и статусы шагов | `roadmap.yaml` |
| Записи по дням | `journal/YYYY-MM-DD.md` |
| Шаблон страницы | `web/page.html` |
| Сборка | `build.py`, Actions → GitHub Pages |

Сам кластер, терраформ и подробные конспекты живут в приватных репозиториях.
Карточки для повторения — [devops-anki](https://tsim0710.github.io/devops-anki/).

## Локально

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python build.py --validate
.venv/bin/python build.py && open site/index.html
```
