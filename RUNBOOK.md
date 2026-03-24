# Runbook VM

Ce runbook explique comment deployer la plateforme sur une VM avec Docker et Docker Compose.

## 1) Prerequis

- Docker installe
- Docker Compose installe
- Ports ouverts: 8080/8501 (edge) et 8090/8601 (security) ou ceux definis dans `.env`

## 2) Recuperer le code

```bash
git clone https://github.com/lmendiboure/Railway-Edge-Testing.git
cd Railway-Edge-Testing
```

## 3) Configurer l'environnement

```bash
cp .env.example .env
```

- Ajuster `SIM_PORT`, `GUI_PORT`, `SECURITY_PORT`, `SECURITY_GUI_PORT`, `GATEWAY_PORT` si besoin

## 4) Lancer les services

```bash
docker compose --profile edge up --build -d
```

Security only:

```bash
docker compose --profile security up --build -d
```

Full stack:

```bash
docker compose --profile edge --profile security up --build -d
```

Gateway (pas de ports dans les URLs):

```bash
docker compose --profile edge --profile security --profile gateway up --build -d
```

## 5) Verifier

```bash
curl http://localhost:8080/agents
curl http://localhost:8080/status/railenium-edge-simulator
curl http://localhost:8090/agents
curl http://localhost:8090/status/railenium-security-simulator
```

GUI:

```
http://<IP_VM>:8501
http://<IP_VM>:8601
```

Gateway:

```
http://<IP_VM>:80/edge/
http://<IP_VM>:80/security/
```

## 6) Demarrer un run de test

```bash
curl -s -X POST http://localhost:8080/control/railenium-edge-simulator \
  -H "Content-Type: application/json" \
  -d '{"action":"start","configuration_name":"example_scenario"}'
```

```bash
curl -s -X POST http://localhost:8090/control/railenium-security-simulator \
  -H "Content-Type: application/json" \
  -d '{"action":"start","configuration_name":"interactive_demo"}'
```

## 6bis) Integration externe (UI / orchestrateur)

Deux approches d'acces aux APIs :

1) Acces direct par ports

- Edge API: `http://<IP_VM>:8080/...`
- Security API: `http://<IP_VM>:8090/...`

Exemples (direct):

```bash
curl http://<IP_VM>:8080/agents
curl http://<IP_VM>:8090/agents
```

2) Acces via gateway (pas de ports dans les URLs)

- Edge API: `http://<IP_VM>/edge-api/...`
- Security API: `http://<IP_VM>/security-api/...`

Exemples (gateway):

```bash
curl http://<IP_VM>/edge-api/agents
curl http://<IP_VM>/security-api/agents
```

Lancer un run (gateway):

```bash
curl -s -X POST http://<IP_VM>/security-api/control/railenium-security-simulator \
  -H "Content-Type: application/json" \
  -d '{"action":"start","configuration_name":"interactive_demo"}'
```

Live control (security):

```bash
curl -s -X POST http://<IP_VM>/security-api/control/railenium-security-simulator \
  -H "Content-Type: application/json" \
  -d '{"action":"set_attack","attack_active":true,"attack_type":"dos","target":"5g","intensity":0.6}'
```

Demarrage differe (start_time):

```bash
curl -s -X POST http://<IP_VM>/edge-api/control/railenium-edge-simulator \
  -H "Content-Type: application/json" \
  -d '{"action":"start","configuration_name":"example_scenario","start_time":"2026-02-18T12:05:00Z"}'
```

## 7) Consulter les logs

```bash
docker compose logs -f edge-simulator
docker compose logs -f edge-gui
docker compose logs -f security-simulator
docker compose logs -f security-gui
```

## 8) Arreter

```bash
docker compose down
```
