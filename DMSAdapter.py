import json
import time
import logging
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
# ----------------------------

from rabbitmq import RabbitMQClient

class DMSAdapter(RabbitMQClient):
    """
    DMSAdapter handles communication between the DMS system and other services
    via RabbitMQ. It consumes messages from 'dms_queue' and publishes responses.
    """
    def __init__(self):
        super().__init__() # Initialize RabbitMQClient with parameters from .env
        self.dms_queue_name = 'dms_queue' # Queue for messages intended for DMS
        self.dms_dl_exchange = 'dms_dlx'
        self.dms_dl_queue = 'dms_dead_letter_queue'
        self.connect()
        if self.channel:
            # Declare a topic exchange for routing messages
            self.declare_exchange(self.exchange_name, 'topic')
            # Declare dead-letter queue and exchange for failed messages
            self.declare_dead_letter_queue_and_exchange(self.dms_dl_queue, self.dms_dl_exchange)
            # Declare the main DMS queue with dead-lettering configured
            self.declare_queue(self.dms_queue_name, self.dms_dl_exchange, 'dms.dead_letter')

            # Bind the DMS queue to listen for all requests directed to DMS
            self.bind_queue(self.dms_queue_name, self.exchange_name, "1c.request.dms.#")
            self.bind_queue(self.dms_queue_name, self.exchange_name, "crm.request.dms.#")
            logger.info(f"DMS Adapter is listening for messages on queue '{self.dms_queue_name}'.")

    def _create_user_in_dms(self, user_payload):
        """
        Simulates creating a user in DMS.
        In a real-world scenario, this would be an API call to the DMS system.
        """
        logger.info(f"Simulating user creation in DMS for payload: {user_payload}")
        time.sleep(2)  # Simulate a 2-second delay

        # In a real-world scenario, a requests.post() would be here.
        # Example: response = requests.post(dms_api_url, json=user_payload)

        # Simulate a successful response
        dms_user_id = f"DMS-USER-{int(time.time())}"
        response = {
            "status": "success",
            "message": "User created successfully in DMS.",
            "dms_user_id": dms_user_id
        }
        return response

    def _get_policy_info_from_dms(self, policy_number):
        """
        Simulates getting policy information from DMS.
        In a real-world scenario, this would be an API call to the DMS system.
        """
        logger.info(f"Simulating getting policy info from DMS for policy number: {policy_number}")
        time.sleep(1)  # Simulate a 1-second delay

        # In a real-world scenario, a requests.get() would be here.
        # Example: response = requests.get(f"{dms_api_url}/policies/{policy_number}")

        # Simulate a successful response
        response = {
            "status": "success",
            "policy_number": policy_number,
            "insurer_name": "Иванов Иван Иванович",
            "policy_status": "Активный",
            "start_date": "2025-01-01",
            "end_date": "2026-01-01"
        }
        return response

    def _process_message(self, ch, method, properties, body):
        """
        Callback function to process incoming messages for the DMS adapter.
        Handles message deserialization, retries, and routing based on message type.
        """
        MAX_RETRIES = 3  # Maximum number of message processing attempts
        try:
            message = json.loads(body)
            logger.info(f"\n[DMS] Received message: {message}")
            retries = message.get('retries', 0)
            message['retries'] = retries + 1
            source_system = message.get("source_system")
            message_type = message.get("message_type")
            payload = message.get("payload")
            request_id = message.get("request_id")

            if not all([source_system, message_type, payload, request_id]):
                logger.error("Message is missing required fields. Rejecting.")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                return

            if message_type == "create_user":
                response_payload = self._create_user_in_dms(payload)
                response_message = {
                    "source_system": "DMS",
                    "target_system": source_system,
                    "message_type": "user_created_response",
                    "payload": response_payload,
                    "request_id": request_id,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
                }
                self.publish_response_message(response_message, f"dms.response.{source_system}.user_created")
                ch.basic_ack(delivery_tag=method.delivery_tag)

            elif message_type == "get_policy_info":
                policy_number = payload.get("policy_number")
                if policy_number:
                    policy_info = self._get_policy_info_from_dms(policy_number)
                    response_message = {
                        "source_system": "DMS",
                        "target_system": source_system,
                        "message_type": "policy_info_response",
                        "payload": policy_info,
                        "request_id": request_id,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
                    }
                    self.publish_response_message(response_message, f"dms.response.{source_system}.policy_info_response")
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                else:
                    logger.error(f"Invalid payload for 'get_policy_info' message. Rejecting.")
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

            else:
                logger.warning(f"Unknown message type '{message_type}'. Rejecting.")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON message. Error: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        except Exception as e:
            logger.error(f"An unexpected error occurred: {e}", exc_info=True)
            if retries < MAX_RETRIES:
                logger.warning(f"Unexpected error (Attempt {retries}). Re-queueing...")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            else:
                logger.error(f"Unexpected error after {MAX_RETRIES} attempts. Sending to DLQ.")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

    def start_consuming(self):
        """
        Starts consuming messages from the DMS queue.
        """
        if self.channel:
            self.channel.basic_consume(
                queue=self.dms_queue_name,
                on_message_callback=self._process_message,
                auto_ack=False
            )
            logger.info("DMS Adapter is waiting for messages. To exit, press CTRL+C.")
            try:
                self.channel.start_consuming()
            except KeyboardInterrupt:
                logger.info("Stopping DMS adapter.")
            finally:
                self.close()

if __name__ == '__main__':
    adapter = DMSAdapter()
    adapter.start_consuming()
