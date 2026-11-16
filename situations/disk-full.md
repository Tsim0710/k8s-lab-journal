---
title: На ноде кончилось место
checked: '2026-11-16'
journal: ['2026-11-16']
---

## Простыми словами

Когда на ноде остаётся меньше 10% диска, kubelet спасает её сам: сначала удаляет неиспользуемые
образы контейнеров, потом выселяет поды. Снаружи это выглядит не как «диск полный», а как хаос:
поды переезжают, перезапускаются, качают образы заново — и снова забивают диск. Место прыгает
туда-сюда, а пороговые алерты с долгим `for` не успевают сработать.

## Как разбирать

1. `kubectl describe node <нода>` — условие `DiskPressure`, события `EvictionThresholdMet`,
   `FreeDiskSpaceFailed`, `ImageGCFailed`
2. Выселенные поды: `kubectl get pods -A | grep Evicted` — с какой ноды и сколько
3. На ноде (`make ssh-w3` и т. п.): `df -h /`, кто занял — `sudo du -xh --max-depth=2 / | sort -h | tail`;
   образы — `sudo crictl images`
4. Тома local-path — `sudo du -sh /opt/local-path-provisioner/*`

## Как чинить

- Найти и удалить источник: чужой большой файл, разросшиеся логи, том Prometheus или Loki
  (`retention` в values)
- После освобождения — убрать выселенные поды: `kubectl delete pods -A --field-selector
  status.phase=Failed`
- Поды вернутся и заново скачают образы — первые минуты нода будет медленной

## Чтобы не повторилось

Алерт раньше порога kubelet: `NodeDiskNearEviction` срабатывает на 15% с учётом минимума за 15 минут
— скачки после чистки его не сбрасывают. Давление на ноде — `NodeUnderPressure`.

## Было у нас

16.11, день поломок: на `k8s-w3` оставили 4%. `DiskPressure` — через 32 секунды, kubelet удалил все
образы и выселял Alloy по кругу, свободное место прыгало между 4 и 16%. За 25 минут в Telegram не
пришло ничего: `NodeFilesystemAlmostOutOfSpace` ждёт меньше 5% полчаса подряд, а kubelet так низко
не пускает; `KubeNodePressure` был info без namespace и глушился InfoInhibitor.
