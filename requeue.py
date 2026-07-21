import asyncio
import os
import sys
import aio_pika

async def main():
    worker_name = sys.argv[1]
    queue_name = f"neurox.{worker_name}"
    dead_name = f"neurox.{worker_name}.dead"
    
    connection = await aio_pika.connect_robust(os.environ["RABBITMQ_URL"])
    async with connection:
        channel = await connection.channel()
        dead_queue = await channel.declare_queue(dead_name, durable=True, arguments={"x-queue-type": "quorum"})
        events_exchange = await channel.declare_exchange("neurox.events", aio_pika.ExchangeType.TOPIC, durable=True)
        
        count = 0
        while True:
            try:
                message = await dead_queue.get(timeout=1, no_ack=False)
                # Re-publish to events exchange using original routing key or publish to default
                routing_key = message.routing_key or "#"
                await channel.default_exchange.publish(
                    aio_pika.Message(body=message.body, headers=message.headers),
                    routing_key=queue_name
                )
                await message.ack()
                count += 1
            except aio_pika.exceptions.QueueEmpty:
                break
        print(f"Moved {count} messages from {dead_name} to {queue_name}.")

if __name__ == "__main__":
    asyncio.run(main())
