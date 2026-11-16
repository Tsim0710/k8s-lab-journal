---
title: Компонент кластера пропал
alerts: [KubeAPIDown, KubeSchedulerDown, KubeControllerManagerDown, KubeProxyDown, KubeletDown, TargetDown, KubeAPIInstanceUnreachable, KubeControllerManagerInstanceUnreachable, KubeletInstanceUnreachable, KubeProxyInstanceUnreachable, KubeSchedulerInstanceUnreachable]
---

## Простыми словами

Prometheus не видит компонент: серии `up` для него нет совсем или цель не отвечает. Это может значить,
что компонент упал, — а может, что ослеп сам Prometheus. **Сначала проверь мониторинг, потом
компонент.**

## Чем грозит

apiserver — кластером нельзя управлять. scheduler — новые поды не ставятся. controller-manager — не
работают контроллеры (реплики, выселения). kubelet — нода не управляется.

## Что проверить

1. **Жив ли компонент на самом деле:** `kubectl get pods -n kube-system -o wide` (статические поды
   control plane), `kubectl get nodes`. Всё живо — проверяй мониторинг
2. Цели в Prometheus: Status → Targets — есть ли ошибка (`connection refused`, таймаут)
3. Пишет ли Prometheus вообще: `count by (job) (up == 1)` в Explore. Пусто при живых целях —
   [Prometheus не пишет данные](prometheus-no-data.html)
4. `connection refused` на scheduler / controller-manager / etcd — метрики слушают только
   `127.0.0.1`; у нас это открыто в `stage2/kubeadm-config.yaml`

## Как починить

- Компонент control plane лёг — на мастере `make ssh-cp`, `sudo crictl ps -a | grep kube-`, логи
  контейнера; манифесты — `/etc/kubernetes/manifests`, править только через `kubeadm-config`
- kubelet — [нода NotReady](node-not-ready.html)
- Слепой Prometheus — по его runbook

## Когда звать на помощь

apiserver недоступен и мастер не отвечает — у нас один мастер, резерва нет. Снимок etcd есть в
`~/lab-backups`, восстановление — `make etcd-tool`.

## Было у нас

[10.11.2026](../journal/2026-11-10.html): четыре `*Down` при живых компонентах — ослеп Prometheus.
Ложная гипотеза про `127.0.0.1` съела время.
