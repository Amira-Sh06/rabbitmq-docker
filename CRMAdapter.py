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

class CRMAdapter(RabbitMQClient):
    """
    CRMAdapter handles communication between the CRM system and other services
    via RabbitMQ. It consumes messages from 'crm_queue' and publishes responses.
    """
    def __init__(self):
        super().__init__() # Initialize RabbitMQClient with parameters from .env
        self.crm_queue_name = 'crm_queue'
        self.crm_dl_exchange = 'crm_dlx'
        self.crm_dl_queue = 'crm_dead_letter_queue'
        self.connect()
        if self.channel:
            # Declare a topic exchange for routing messages
            self.declare_exchange(self.exchange_name, 'topic')
            # Declare dead-letter queue and exchange for failed messages
            self.declare_dead_letter_queue_and_exchange(self.crm_dl_queue, self.crm_dl_exchange)
            # Declare the main CRM queue with dead-lettering configured
            self.declare_queue(self.crm_queue_name, self.crm_dl_exchange, 'crm.dead_letter')

            # Bind the CRM queue to listen for CRM requests and responses for CRM
            self.bind_queue(self.crm_queue_name, self.exchange_name, "*.request.crm.#")
            self.bind_queue(self.crm_queue_name, self.exchange_name, "dms.response.crm.#")
            logger.info(f"CRM Adapter is listening for messages on queue '{self.crm_queue_name}'.")

    def _process_message(self, ch, method, properties, body):
        """
        Callback function to process incoming messages for the CRM adapter.
        Handles message deserialization, retries, and routing based on message type.
        """
        MAX_RETRIES = 3 # Maximum number of message processing attempts
        try:
            message = json.loads(body)
            logger.info(f"\n[CRM] Received message: {message}")

            retries = message.get('retries', 0)
            message['retries'] = retries + 1

            source_system = message.get("source_system")
            message_type = message.get("message_type")
            payload = message.get("payload")
            request_id = message.get("request_id")

            # --- ACTUAL CRM SYSTEM ACTIONS ---
            # This section would typically involve calling the real CRM system's API,
            # writing data to its database, or interacting with its internal services.
            if message_type == "update_order_status":
                logger.info(f"[CRM] Processing order status update from {source_system} for order: {payload.get('order_id')}")
                try:
                    # Simulate updating data in CRM
                    # crm_api_client.update_order(payload['order_id'], {'status': payload['status']})
                    crm_internal_id = "CRM_ORD_" + str(int(time.time()))
                    logger.info(f"[CRM] Order '{payload.get('order_id')}' status updated in CRM.")
                    status = "success"
                except Exception as e:
                    logger.error(f"[CRM] Error updating order status in CRM: {e}", exc_info=True)
                    status = "failed"
                    crm_internal_id = None

                # Publish a response back to the source system (e.g., 1C)
                response_message = {
                    "source_system": "CRM",
                    "target_system": source_system,
                    "message_type": "order_status_updated_response",
                    "payload": {"order_id": payload.get("order_id"), "new_status": status, "crm_internal_id": crm_internal_id},
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "request_id": request_id
                }
                self.publish_message(self.exchange_name, f"crm.response.{source_system.lower()}.order_status_updated", response_message)

                # Optional: If CRM needs to get data from DMS
                if payload.get("needs_policy_info"): # Assuming 1C requested this
                    request_dms_message = {
                        "source_system": "CRM",
                        "target_system": "DMS",
                        "message_type": "get_policy_info",
                        "payload": {"policy_number": "POL-" + payload.get("order_id")},
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "request_id": request_id # Maintain request_id to link DMS response to this CRM request
                    }
                    self.publish_message(self.exchange_name, "crm.request.dms.get_policy_info", request_dms_message)
                    logger.info(f"[CRM] Requested policy info from DMS for order {payload.get('order_id')}.")

            elif message_type == "policy_info_response":
                logger.info(f"[CRM] Received policy information from DMS: {payload} for request_id: {request_id}")
                # --- ACTUAL CRM SYSTEM ACTION ---
                # Here, CRM can update its data based on the received policy information.
                # For example, crm_api_client.update_customer_policy(payload['insured_name'], payload)
                logger.info(f"[CRM] Updating CRM records with policy info for request_id: {request_id}.")

            else:
                logger.warning(f"[CRM] Unhandled message type: {message_type} from {source_system}. Rejecting message: {message}")
                self.nack_message(method, requeue=False) # Negative acknowledgment, do not re-queue
                return

            self.acknowledge_message(method) # Acknowledge successful processing

        except json.JSONDecodeError:
            logger.error(f"[CRM] Error: Invalid JSON received, rejecting message: {body.decode()}", exc_info=True)
            self.reject_message(method, requeue=False) # Reject message, do not re-queue
        except Exception as e:
            logger.exception(f"[CRM] Unhandled error processing message (attempt {message.get('retries', 1)}/{MAX_RETRIES}): {e}")
            if message['retries'] < MAX_RETRIES:
                self.nack_message(method, requeue=True) # Negative acknowledgment, re-queue
            else:
                logger.critical(f"[CRM] Message failed after {MAX_RETRIES} attempts, sending to DLX: {message}")
                self.nack_message(method, requeue=False) # Negative acknowledgment, send to DLX

    def start(self):
        """
        Starts the CRM adapter, begins consuming messages from its queue.
        """
        if self.channel:
            self.start_consuming(self.crm_queue_name, self._process_message)
        else:
            logger.error("Failed to initialize CRM Adapter. Check RabbitMQ connection.")

if __name__ == "__main__":
    crm_adapter = CRMAdapter()
    crm_adapter.start()
    crm_adapter.close()