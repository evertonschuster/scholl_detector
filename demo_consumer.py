import json
import os

import pika

host = os.getenv("RABBITMQ_HOST", "localhost")
port = int(os.getenv("RABBITMQ_PORT", "5672"))
username = os.getenv("RABBITMQ_USER", "guest")
password = os.getenv("RABBITMQ_PASS", "guest")
exchange = os.getenv("RABBITMQ_EXCHANGE", "classroom.events")

credentials = pika.PlainCredentials(username, password)
params = pika.ConnectionParameters(host=host, port=port, credentials=credentials)
connection = pika.BlockingConnection(params)
channel = connection.channel()

channel.exchange_declare(exchange=exchange, exchange_type="topic", durable=True)
result = channel.queue_declare(queue="", exclusive=True)
queue_name = result.method.queue
channel.queue_bind(queue=queue_name, exchange=exchange, routing_key="classroom.#")

print("[*] Waiting for events. Press CTRL+C to exit.")


def callback(ch, method, properties, body):
    payload = json.loads(body)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=True)
channel.start_consuming()
