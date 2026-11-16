---
title: Кончается диск
alerts: [NodeDiskNearEviction, NodeFilesystemSpaceFillingUp, NodeFilesystemAlmostOutOfSpace, KubePersistentVolumeInodesFillingUp]
---

## Простыми словами

На диске ноды кончается место (или inode'ы). У нас тома local-path — это каталоги на том же диске
ноды, поэтому этот алерт касается и баз, Prometheus и Loki: отдельных метрик на том у local-path нет.

При 10% свободного kubelet начинает сам удалять образы и выселять поды — поэтому
`NodeDiskNearEviction` срабатывает раньше, на 15%. `NodeFilesystemAlmostOutOfSpace` (меньше 5%) на
воркере может не прийти никогда: kubelet не даёт опуститься так низко надолго.

## Чем грозит

Базы и Prometheus перестают писать, kubelet начинает выселять поды и чистить образы.

## Что проверить

1. Какая нода и раздел — метки `node`, `mountpoint`
2. Что занимает: на ноде `sudo du -xh --max-depth=2 / | sort -h | tail -20`; тома —
   `sudo du -sh /opt/local-path-provisioner/*`
3. Образы: `sudo crictl images` / `sudo ctr -n k8s.io images ls | wc -l`
4. Логи контейнеров: `sudo du -sh /var/log/pods`

## Как починить

- Prometheus / Loki — уменьшить `retention` / `retentionSize` в values
- Старые образы — `sudo crictl rmi --prune`
- Не хватает в принципе — увеличить диск ноды в `infra/variables.tf` (`disk_gb`) и расширить
  файловую систему

## Когда звать на помощь

Меньше 5% и растёт — сначала остановить источник записи, потом разбираться: при 0% базы портят данные.

## Было у нас

16.11, день поломок: на `k8s-w3` осталось 4%. kubelet удалил все образы и выселял поды, свободное место
прыгало между 4 и 16%, ни один готовый алерт так и не дошёл до Telegram. Правило
`NodeDiskNearEviction` написано по итогам.
