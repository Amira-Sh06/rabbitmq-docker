import json
import time
import os
import logging
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Logging Configuration ---
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
# ----------------------------

from rabbitmq import RabbitMQClient

class CreatioCRMAdapter(RabbitMQClient):
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

        self.creatio_url = os.getenv('CRMAdapter_creatio_url')
        self.creatio_auth_url = os.getenv('CREATIO_AUTH_URL')
        self.creatio_update_order_url = os.getenv('CREATIO_UPDATE_ORDER_URL')
        self.creatio_username = os.getenv('CREATIO_USERNAME')
        self.creatio_password = os.getenv('CREATIO_PASSWORD')
        self.session = requests.Session()  # Use a session to save authorization

def authorization(self):
    """
    Method
    for authorizing in Creatio and obtaining session cookies.
    """
    auth_url = self.creatio_url + self.creatio_auth_url
    headers = {'Content-Type': 'application/json'}
    data = json.dumps({
        "Username": self.creatio_username,
        "UserPassword": self.creatio_password
    })

    try:
        response = self.session.post(auth_url, headers=headers, data=data)
        response.raise_for_status()
        logger.info(f"CRM Adapter is responding with status code {response.status_code}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to authenticate with Creatio: {e}", exc_info=True)
        return False

def _update_creatio_order_status(self, order_id, new_status):
    """
    Method for updating order status in Creatio via OData API.
    """
    if not self.session.cookies:
        logger.warning("Creatio session expired or not authenticated. Re-authenticating...")
        if not self._authenticate():
            raise ConnectionError("Failed to authenticate with Creatio.")

    update_url = self.creatio_update_order_url.format(order_id = order_id) + self.creatio.url
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json; odata.metadata=minimal',
        'ForceUseSession': 'true'
    }
    data = json.dumps({
        "Status": {"Name": new_status}  # Это пример, реальная модель данных может отличаться
    })
    try:
        response = self.session.patch(update_url, data=data, headers=headers)
        response.raise_for_status()
        logger.info(f"Order '{order_id}' status updated to '{new_status}' in Creatio.")
        return True, None
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to update Creatio order '{order_id}': {e}", exc_info=True)
        return False, str(e)


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

            if message_type == "update_order_status":
                logger.info(f"[CRM] Processing order status update from {source_system} for order: {payload.get('order_id')}")

                order_id = payload.get('order_id')
                new_status = payload.get('new_status')

                success, error_details = _update_creatio_order_status(payload.get('order_id'), new_status)

                if success:
                    # In the real Creatio system, we would get crm_internal_id from the response.
                    # But for now, we are simulating it, as OData PATCH may not return a response.
                    crm_internal_id = "CRM_ORD_" + str(int(time.time()))
                    status = "success"
                    logger.info(f"[CRM] Order '{order_id}' status updated in Creatio. CRM ID: {crm_internal_id}")

                else:
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
