---
title: Нода NotReady
alerts: [KubeNodeNotReady, KubeNodeUnreachable]
---

## Простыми словами

`NotReady` — не «поды умерли», а «кластер перестал слышать ноду». Причины: умерла машина, остановился
kubelet, сломался runtime, уехали часы, кончились inotify. В kubectl они выглядят одинаково — разница
видна только на самой ноде. Контейнеры на ноде при этом могут продолжать работать.

## Чем грозит

Через ~1.5 минуты трафик на поды ноды прекращается, ещё через 5 минут их выселяют. Deployment'ы
переедут, StatefulSet'ы и всё с томами local-path — нет: диски на этой ноде.

## Что проверить

1. Машина жива: `make lab-status` (`RUNNING`?)
2. Зайти на ноду: `make ssh-w1` (`ssh-w2`, `ssh-w3`, `ssh-cp`). Не пускает — serial-консоль:
   `gcloud compute instances get-serial-port-output <нода> | tail -50`
3. На ноде: `systemctl status kubelet containerd`, `journalctl -u kubelet --since -15min | tail`,
   `date` (часы!), `df -h /`
4. Ошибки `x509` в логе kubelet при нормальной машине — проверь часы

## Как починить

- kubelet / containerd стоят — `sudo systemctl restart containerd kubelet`
- Часы — `sudo chronyc makestep`, потом рестарт kubelet
- Машина не отвечает — stop/start через `gcloud compute instances stop/start` (диск сохранится)

## Когда звать на помощь

Не удалять поды принудительно (`--force`), пока не убедился, что машина мертва: поды на ней могут быть
живы, и получишь два экземпляра — для баз это порча данных.

## Было у нас

[02.11.2026](../journal/2026-11-02.html): оба воркера `NotReady`, причина нашлась только в
serial-консоли — inotify. [06.11.2026](../journal/2026-11-06.html): хронометраж отказа воркера.
[08.11.2026](../journal/2026-11-08.html): kubelet, часы и DNS по отдельности.
