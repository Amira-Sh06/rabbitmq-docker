# rabbitmq.py
import pika
import json
import os
import logging
from dotenv import load_dotenv

load_dotenv() # Load variables from .env

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO, # Can be set to DEBUG for more detailed logs
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
# ----------------------------

class RabbitMQClient:
    """
    A generic RabbitMQ client class for connecting, declaring exchanges/queues,
    publishing, and consuming messages.
    """
    def __init__(self):
        # Read from .env, or use 'localhost'/'guest' as defaults
        self.host = os.getenv('RABBITMQ_HOST', 'localhost')
        self.port = int(os.getenv('RABBITMQ_PORT', 5672))
        self.credentials = pika.PlainCredentials(
            os.getenv('RABBITMQ_USERNAME', 'guest'),
            os.getenv('RABBITMQ_PASSWORD', 'guest')
        )
        self.connection = None
        self.channel = None
        self.exchange_name = 'main_exchange' # Default main exchange to be used

    def connect(self):
        """
        Establishes a connection to RabbitMQ.
        """
        try:
            self.connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=self.host,
                    port=self.port,
                    credentials=self.credentials
                )
            )
            self.channel = self.connection.channel()
            logger.info(f"Connected to RabbitMQ at {self.host}:{self.port}")
        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"Error connecting to RabbitMQ at {self.host}:{self.port}: {e}", exc_info=True)
            self.connection = None
            self.channel = None

    def close(self):
        """
        Closes the RabbitMQ connection.
        """
        if self.connection and not self.connection.is_closed: # Use is_closed to check connection state
            self.connection.close()
            logger.info(f"Disconnected from RabbitMQ at {self.host}:{self.port}.")

    def declare_exchange(self, exchange_name, exchange_type='topic'):
        """
        Declares an exchange.
        """
        if self.channel:
            self.channel.exchange_declare(exchange=exchange_name, exchange_type=exchange_type, durable=True)
            logger.info(f"Exchange '{exchange_name}' declared ({exchange_type}).")

    def declare_queue(self, queue_name, dl_exchange_name=None, dl_routing_key=None):
        """
        Declares a queue, with optional Dead Letter Exchange configuration.
        """
        if self.channel:
            arguments = {}
            if dl_exchange_name and dl_routing_key:
                arguments['x-dead-letter-exchange'] = dl_exchange_name
                arguments['x-dead-letter-routing-key'] = dl_routing_key

            result = self.channel.queue_declare(queue=queue_name, durable=True, arguments=arguments)
            logger.info(f"Queue '{queue_name}' declared. DLX configured: {bool(dl_exchange_name)}")
            return result.method.queue
        return None

    def bind_queue(self, queue_name, exchange_name, routing_key):
        """
        Binds a queue to an exchange with a given routing key.
        """
        if self.channel:
            self.channel.queue_bind(exchange=exchange_name, queue=queue_name, routing_key=routing_key)
            logger.info(f"Queue '{queue_name}' bound to exchange '{exchange_name}' with routing key '{routing_key}'.")

    def unbind_queue(self, queue_name, exchange_name, routing_key):
        """
        Unbinds a queue from an exchange.
        """
        if self.channel:
            self.channel.queue_unbind(exchange=exchange_name, queue=queue_name, routing_key=routing_key)
            logger.info(f"Queue '{queue_name}' unbound from exchange '{exchange_name}' with routing key '{routing_key}'.")

    def publish_message(self, exchange_name, routing_key, message):
        """
        Publishes a message to an exchange with a given routing key.
        The queue_name is not needed here as the exchange handles routing.
        """
        if self.channel:
            try:
                self.channel.basic_publish(
                    exchange=exchange_name,
                    routing_key=routing_key,
                    body=json.dumps(message),
                    properties=pika.BasicProperties(
                        delivery_mode=2,   # Make message persistent
                        content_type='application/json'
                    )
                )
                logger.info(f"Published message to exchange '{exchange_name}' with routing key '{routing_key}': {message}")
                return True
            except Exception as e:
                logger.error(f"Error publishing message to exchange '{exchange_name}' with routing key '{routing_key}': {e}", exc_info=True)
                return False
        return False

    def start_consuming(self, queue_name, callback):
        """
        Starts consuming messages from the specified queue.
        """
        if self.channel:
            logger.info(f"Starting to consume messages from queue '{queue_name}'...")
            self.channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=False) # Important: auto_ack=False
            try:
                self.channel.start_consuming()
            except KeyboardInterrupt:
                logger.info("Stopping consumption due to KeyboardInterrupt.")
            except Exception as e:
                logger.error(f"Error during consumption from queue '{queue_name}': {e}", exc_info=True)
        else:
            logger.error(f"Channel not available for consuming from queue '{queue_name}'.")

    def acknowledge_message(self, method_frame):
        """
        Acknowledges a message, indicating successful processing.
        """
        if self.channel:
            self.channel.basic_ack(delivery_tag=method_frame.delivery_tag)
            # logger.debug(f"Acknowledged message with delivery tag: {method_frame.delivery_tag}") # Can be added, but be careful with log volume

    def reject_message(self, method_frame, requeue=False):
        """
        Rejects a message. If requeue=False, it may go to the DLX.
        """
        if self.channel:
            self.channel.basic_reject(delivery_tag=method_frame.delivery_tag, requeue=requeue)
            logger.warning(f"Rejected message with delivery tag: {method_frame.delivery_tag}, requeue={requeue}")

    def nack_message(self, method_frame, requeue=True):
        """
        Negative acknowledges (Nacks) a message. More flexible than reject.
        """
        if self.channel:
            self.channel.basic_nack(delivery_tag=method_frame.delivery_tag, requeue=requeue)
            logger.warning(f"Nacked message with delivery tag: {method_frame.delivery_tag}, requeue={requeue}")

    def declare_dead_letter_queue_and_exchange(self, dl_queue_name, dl_exchange_name):
        """
        Declares a Dead Letter Exchange and its associated Dead Letter Queue.
        Messages that are rejected or Nacked (without requeue) will be routed here.
        """
        if self.channel:
            self.channel.exchange_declare(exchange=dl_exchange_name, exchange_type='topic', durable=True)
            self.channel.queue_declare(queue=dl_queue_name, durable=True)
            self.channel.queue_bind(exchange=dl_exchange_name, queue=dl_queue_name, routing_key='#') # '#' catches everything sent to the DLX
            logger.info(f"Dead letter exchange '{dl_exchange_name}' and queue '{dl_queue_name}' declared and bound.")
