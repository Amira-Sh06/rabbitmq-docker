import json
import time
import os
import logging
import base64
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
    CreatioCRMAdapter handles communication between the Creatio CRM system
    and other services via RabbitMQ. It consumes messages from 'crm_queue'
    and publishes responses.
    """

    def __init__(self):
        super().__init__()
        self.crm_queue_name = 'crm_queue'
        self.crm_dl_exchange = 'crm_dlx'
        self.crm_dl_queue = 'crm_dead_letter_queue'
        self.connect()
        if self.channel:
            self.declare_exchange(self.exchange_name, 'topic')
            self.declare_dead_letter_queue_and_exchange(self.crm_dl_queue, self.crm_dl_exchange)
            self.declare_queue(self.crm_queue_name, self.crm_dl_exchange, 'crm.dead_letter')
            self.bind_queue(self.crm_queue_name, self.exchange_name, "*.request.crm.#")
            self.bind_queue(self.crm_queue_name, self.exchange_name, "dms.response.crm.#")
            logger.info(f"CRM Adapter is listening for messages on queue '{self.crm_queue_name}'.")

        # Configuration variables from environment, for both real and fake CRM
        self.creatio_url = os.getenv('CREATIO_URL')
        self.creatio_auth_url = os.getenv('CREATIO_AUTH_URL')
        self.creatio_update_order_url = os.getenv('CREATIO_UPDATE_ORDER_URL')
        self.creatio_username = os.getenv('CREATIO_USERNAME')
        self.creatio_password = os.getenv('CREATIO_PASSWORD')
        self.session = requests.Session()

    def _authenticate(self):
        """
        Authenticates with the Creatio CRM system to obtain a session cookie.
        """
        auth_url = self.creatio_url + self.creatio_auth_url
        headers = {'Content-Type': 'application/json'}
        data = json.dumps({
            "UserName": self.creatio_username,
            "UserPassword": self.creatio_password
        })

        try:
            response = self.session.post(auth_url, headers=headers, data=data)
            response.raise_for_status()
            logger.info(f"CRM Adapter received status code {response.status_code} during authentication.")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to authenticate with Creatio: {e}", exc_info=True)
            return False

    def _update_creatio_order_status(self, order_id, new_status):
        """
        Updates the status of an order in Creatio via OData API.
        """
        if not self.session.cookies:
            logger.warning("Creatio session expired or not authenticated. Re-authenticating...")
            if not self._authenticate():
                raise ConnectionError("Failed to authenticate with Creatio.")

        update_url = self.creatio_url + self.creatio_update_order_url.format(order_id=order_id)
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json; odata.metadata=minimal',
            'ForceUseSession': 'true'
        }
        data = json.dumps({
            "Status": {"Name": new_status}
        })

        try:
            response = self.session.patch(update_url, data=data, headers=headers)
            response.raise_for_status()
            logger.info(f"Order '{order_id}' status updated to '{new_status}' in Creatio.")
            return True, None
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to update Creatio order '{order_id}': {e}", exc_info=True)
            return False, str(e)

    def _get_policy_info_from_creatio(self, request_id, policy_number):
        """
        Simulates retrieving policy information from Creatio.
        In a real scenario, this would be an API call to the Creatio system.
        """
        logger.info(f"Simulating retrieving policy info for policy number: {policy_number}")
        # In a real-world scenario, a requests.get() would be here.
        # Example: response = self.session.get(f"{self.creatio_url}/api/policies/{policy_number}")
        time.sleep(1)  # Simulate network latency

        policy_info = {
            "policy_number": policy_number,
            "policy_id": "CRM-POLICY-" + str(int(time.time())),
            "status": "Active",
            "coverage_details": "Comprehensive"
        }
        return policy_info

    def _save_pdf_file(self, filename, file_data_base64):
        """
        Decodes a Base64 string and saves it as a PDF file.
        This simulates receiving and storing a file in the CRM system.
        """
        try:
            file_data = base64.b64decode(file_data_base64)
            filepath = f"/crm_storage/{filename}" # Assuming a directory inside the container
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "wb") as f:
                f.write(file_data)
            logger.info(f"PDF file '{filename}' saved successfully in CRM.")
            return True
        except Exception as e:
            logger.error(f"Failed to save PDF file '{filename}': {e}", exc_info=True)
            return False

    def _process_message(self, ch, method, properties, body):
        """
        Callback function to process incoming messages for the CRM adapter.
        Handles message deserialization, retries, and routing based on message type.
        """
        MAX_RETRIES = 3  # Maximum number of message processing attempts
        try:
            message = json.loads(body)
            logger.info(f"\n[CRM] Received message: {message}")
            retries = message.get('retries', 0)
            message['retries'] = retries + 1
            source_system = message.get("source_system")
            message_type = message.get("message_type")
            payload = message.get("payload")
            request_id = message.get("request_id")

            #  New logic to handle PDF files
            if message_type == "send_pdf_file":
                filename = payload.get("filename")
                file_data_base64 = payload.get("file_data_base64")
                if filename and file_data_base64:
                    if self._save_pdf_file(filename, file_data_base64):
                        response_message = {
                            "status": "success",
                            "message": f"PDF file '{filename}' received and saved in CRM.",
                            "source_system": "CRM",
                            "target_system": source_system,
                            "request_id": request_id,
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
                        }
                        self.publish_response_message(response_message, f"crm.response.{source_system}.pdf_received")
                        ch.basic_ack(delivery_tag=method.delivery_tag)
                    else:
                        logger.error(f"Failed to process PDF file. Sending to DLQ.")
                        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                else:
                    logger.error(f"Invalid payload for 'send_pdf_file' message. Rejecting.")
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

            # Validate required fields
            if not all([source_system, message_type, payload, request_id]):
                logger.error("Message is missing required fields. Rejecting.")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                return

            if message_type == "update_order_status":
                order_id = payload.get("order_id")
                new_status = payload.get("new_status")

                if order_id and new_status:
                    success, error_message = self._update_creatio_order_status(order_id, new_status)
                    if success:
                        # Publish a success response
                        response_message = {
                            "status": "success",
                            "message": f"Order {order_id} status updated to {new_status} in CRM.",
                            "source_system": "CRM",
                            "target_system": source_system,
                            "request_id": request_id,
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
                        }
                        self.publish_response_message(response_message,
                                                      f"crm.response.{source_system}.order_status_updated")
                        ch.basic_ack(delivery_tag=method.delivery_tag)
                    else:
                        # Handle failure and possibly requeue or nack
                        if retries < MAX_RETRIES:
                            logger.warning(f"Failed to update order {order_id} (Attempt {retries}). Re-queueing...")
                            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                        else:
                            logger.error(
                                f"Failed to update order {order_id} after {MAX_RETRIES} attempts. Sending to DLQ.")
                            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                else:
                    logger.error(f"Invalid payload for 'update_order_status' message. Rejecting.")
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

            elif message_type == "policy_info_response":
                policy_info = payload
                logger.info(f"Received policy info from DMS: {policy_info}")
                # Logic to process the policy info in CRM would go here
                ch.basic_ack(delivery_tag=method.delivery_tag)
                # Example of follow-up action:
                # self.process_policy_info_in_crm(policy_info)

            else:
                logger.warning(f"Unknown message type '{message_type}'. Rejecting.")
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode JSON message. Error: {e}")
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
        except ConnectionError as e:
            logger.error(f"Connection error: {e}. Re-queueing message.")
            if retries < MAX_RETRIES:
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            else:
                logger.error(f"Connection error after {MAX_RETRIES} attempts. Sending to DLQ.")
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
        Starts consuming messages from the CRM queue.
        """
        if self.channel:
            self.channel.basic_consume(
                queue=self.crm_queue_name,
                on_message_callback=self._process_message,
                auto_ack=False
            )
            logger.info("CRM Adapter is waiting for messages. To exit, press CTRL+C.")
            try:
                self.channel.start_consuming()
            except KeyboardInterrupt:
                logger.info("Stopping CRM adapter.")
            finally:
                self.close()


if __name__ == '__main__':
    adapter = CreatioCRMAdapter()
    adapter.start_consuming()
