# Classroom Observables MVP

MVP de um sistema que consome streams RTSP, detecta sinais **observáveis** e publica eventos agregados para apoio pedagógico e segurança. O foco é **privacidade**: sem armazenamento de vídeo bruto e apenas metadados agregados.

## Funcionalidades
- Ingestão de RTSP/arquivo com reconexão e amostragem (FPS configurável).
- Detecção de pessoas (YOLOv8n se disponível, caso contrário stub).
- Tracking efêmero para evitar duplicidade em janelas curtas.
- Zonas configuráveis via polígonos no `config.yml`.
- Métricas por minuto: contagem de pessoas e nível de movimento.
- Eventos: `fall`, `physical_conflict_risk`, `crowd_surge`.
- Envio de eventos via RabbitMQ (exchange `topic`).
- API FastAPI para consultas agregadas.

## Privacidade
- Não salva vídeo bruto por padrão.
- Eventos sensíveis marcados com `requires_review: true`.
- Apenas metadados e agregados são persistidos.

## Estrutura
- `app/`: código principal (API, pipeline, modelos).
- `config.yml`: exemplo de configuração com 2 salas.
- `demo_consumer.py`: consumidor de eventos RabbitMQ.

## Como executar (Docker)
```bash
docker-compose up --build
```

- API: `http://localhost:8000/health`
- RabbitMQ UI: `http://localhost:15672` (guest/guest)

## Como executar localmente
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# API
python -m app.cli api

# Pipeline (RTSP)
python -m app.cli pipeline
```

## API
- `GET /health`
- `GET /rooms/{room_id}/summary?from=&to=`
- `GET /rooms/{room_id}/events?from=&to=&type=`
- `GET /rooms/{room_id}/timeseries?metric=person_count|motion_level&from=&to=`

## Mensagens na fila (schema v1)
```json
{
  "schema_version":"1.0",
  "event_id":"<uuid4>",
  "room_id":"<string>",
  "camera_id":"<string>",
  "timestamp_utc":"<ISO8601>",
  "event_type":"fall|physical_conflict_risk|crowd_surge|activity_level|person_count|hand_raise",
  "severity":1,
  "confidence":0.6,
  "zone_id":"front|middle|back|custom",
  "counts":{"persons":0},
  "activity":{"motion_level":0.0},
  "track":{"ephemeral_track_id":"<string>", "persist_scope":"session_only"},
  "requires_review": true,
  "privacy":{"faces_blurred":true,"frame_stored":false},
  "debug":{"model_versions":{}}
}
```

## Configuração
- Ajuste `config.yml` para suas salas, câmeras e zonas.
- `DATABASE_URL` e `RABBITMQ_*` podem ser definidos via variáveis de ambiente.

## Testes
```bash
pytest
```
