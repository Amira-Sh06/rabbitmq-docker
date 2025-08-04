import json
import time
import os
import logging
import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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

    def _process_message(self, ch, method, properties, body):
        # ... (rest of the processing logic is the same)
        # ...
        pass # Placeholder for brevity, assuming the logic remains unchanged

    def start_consuming(self):
        # ... (rest of the consuming logic is the same)
        # ...
        pass # Placeholder for brevity, assuming the logic remains unchanged

if __name__ == '__main__':
    adapter = CreatioCRMAdapter()
    adapter.start_consuming()
