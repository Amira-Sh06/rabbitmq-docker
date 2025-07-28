import json
import time
import logging
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
            self.bind_queue(self.dms_queue_name, self.exchange_name, "*.request.dms.#")
            logger.info(f"DMS Adapter is listening for messages on queue '{self.dms_queue_name}'.")

    def _process_message(self, ch, method, properties, body):
        """
        Callback function to process incoming messages for the DMS adapter.
        Handles message deserialization, retries, and routing based on message type.
        """
        MAX_RETRIES = 3 # Maximum number of message processing attempts
        try:
            message = json.loads(body)
            logger.info(f"\n[DMS] Received message: {message}")

            retries = message.get('retries', 0)
            message['retries'] = retries + 1

            source_system = message.get("source_system")
            message_type = message.get("message_type")
            payload = message.get("payload")
            request_id = message.get("request_id")

            # --- ACTUAL DMS SYSTEM ACTIONS ---
            # This section would typically involve calling the real DMS system's API,
            # writing data to its database, or interacting with its internal services.
            if message_type == "create_user":
                logger.info(f"[DMS] Processing user creation request from {source_system} for user: {payload.get('name')}")
                try:
                    # Simulate calling DMS API
                    # dms_api_client.create_user(payload)
                    dms_internal_id = "DMS_USR_" + str(int(time.time())) # ID obtained from actual DMS
                    logger.info(f"[DMS] User '{payload.get('name')}' successfully created in DMS with ID: {dms_internal_id}")
                    status = "success"
                except Exception as e:
                    logger.error(f"[DMS] Error creating user in DMS: {e}", exc_info=True)
                    status = "failed"
                    dms_internal_id = None

                # Publish a response back to the source system (e.g., 1C or CRM)
                response_message = {
                    "source_system": "DMS",
                    "target_system": source_system, # Respond back to the requesting system
                    "message_type": "user_created_response",
                    "payload": {"user_id": payload.get("user_id"), "status": status, "dms_id": dms_internal_id},
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "request_id": request_id # Pass request_id back
                }
                self.publish_message(self.exchange_name, f"dms.response.{source_system.lower()}.user_created", response_message)

            elif message_type == "get_policy_info":
                logger.info(f"[DMS] Processing policy info request from {source_system} for policy: {payload.get('policy_number')}")
                try:
                    # Simulate fetching data from DMS
                    # policy_info = dms_api_client.get_policy_details(payload['policy_number'])
                    policy_info = {
                        "policy_number": payload.get("policy_number"),
                        "status": "active",
                        "insured_name": "ООО Ромашка", # Example data
                        "coverage_amount": 1000000.00
                    }
                    logger.info(f"[DMS] Retrieved policy info: {policy_info}")
                except Exception as e:
                    logger.error(f"[DMS] Error getting policy info from DMS: {e}", exc_info=True)
                    policy_info = {"policy_number": payload.get("policy_number"), "status": "error", "error_details": str(e)}

                response_message = {
                    "source_system": "DMS",
                    "target_system": source_system,
                    "message_type": "policy_info_response",
                    "payload": policy_info,
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "request_id": request_id
                }
                self.publish_message(self.exchange_name, f"dms.response.{source_system.lower()}.policy_info", response_message)

            else:
                logger.warning(f"[DMS] Unhandled message type: {message_type} from {source_system}. Rejecting message: {message}")
                self.nack_message(method, requeue=False) # Negative acknowledgment, do not re-queue
                return

            self.acknowledge_message(method) # Acknowledge successful processing

        except json.JSONDecodeError:
            logger.error(f"[DMS] Error: Invalid JSON received, rejecting message: {body.decode()}", exc_info=True)
            self.reject_message(method, requeue=False) # Reject message, do not re-queue
        except Exception as e:
            logger.exception(f"[DMS] Unhandled error processing message (attempt {message.get('retries', 1)}/{MAX_RETRIES}): {e}")
            if message['retries'] < MAX_RETRIES:
                self.nack_message(method, requeue=True) # Negative acknowledgment, re-queue
            else:
                logger.critical(f"[DMS] Message failed after {MAX_RETRIES} attempts, sending to DLX: {message}")
                self.nack_message(method, requeue=False) # Negative acknowledgment, send to DLX

    def start(self):
        """
        Starts the DMS adapter, begins consuming messages from its queue.
        """
        if self.channel:
            self.start_consuming(self.dms_queue_name, self._process_message)
        else:
            logger.error("Failed to initialize DMS Adapter. Check RabbitMQ connection.")

if __name__ == "__main__":
    dms_adapter = DMSAdapter()
    dms_adapter.start()
    dms_adapter.close()