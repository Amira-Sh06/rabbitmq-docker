# Enterprise System Integration with RabbitMQ and Docker

This project demonstrates a foundational approach to integrating various enterprise systems (like **1C**, **DMS**, and **CRM**) using **RabbitMQ** as a central message broker. 
The architecture emphasizes asynchronous communication, loose coupling, and resilience through features like Dead Letter Queues (DLQs).

It provides a practical example of how different business systems can exchange information reliably without direct, synchronous API dependencies, making the overall integration more robust and scalable.

---

## Requirements

* **Python 3.9+**
* **Docker** and **Docker Compose** installed on your system.
    * [Install Docker Engine](https://docs.docker.com/engine/install/)
    * [Install Docker Compose](https://docs.docker.com/compose/install/)

---

## Project Architecture

The project consists of several Python-based adapter services, each communicating with a central RabbitMQ broker. The Flask application within the `OneCAdapter.py` serves as an HTTP entry point for the 1C system.

```
.
├── CRMAdapter.py        # Adapter for the CRM system
├── DMSAdapter.py        # Adapter for the DMS system
├── docker-compose.yml   # Docker Compose configuration for all services
├── Dockerfile_CRM       # Dockerfile for the CRM adapter service
├── Dockerfile_DMS       # Dockerfile for the DMS adapter service
├── Dockerfile_OneC      # Dockerfile for the 1C adapter service
├── OneCAdapter.py       # Adapter for the 1C system (includes Flask HTTP server)
├── rabbitmq.py          # Reusable RabbitMQ client class
├── README.md            # This file
└── requirements.txt     # Python dependencies
```

### Purpose of `FakeCreatio.py`

Since a real CRM system was not available for this project, `FakeCreatio.py` was created to serve as a mock API endpoint. It mimics the authentication and data update logic of a real CRM, allowing the `CRMAdapter.py` to be fully tested and demonstrated within a self-contained Docker environment. It is an essential component for running the project in a demo setting.

### System Overview

* **1C Adapter (`OneCAdapter.py`):**
    * **HTTP Endpoint:** Exposes Flask API endpoints (`/send_to_dms`, `/send_to_crm`) for 1C to send requests.
    * **RabbitMQ Publisher:** Publishes messages from 1C to the `main_exchange` with specific routing keys (e.g., `1c.request.dms.create_user`).
    * **RabbitMQ Consumer:** Listens to the `1c_queue` for responses from DMS and CRM, processing acknowledgments or data updates relevant to 1C.
* **DMS Adapter (`DMSAdapter.py`):**
    * **RabbitMQ Consumer:** Listens to the `dms_queue` for requests (e.g., `create_user`, `get_policy_info`) from other systems (1C, CRM).
    * **Simulated Processing:** Simulates interactions with a real DMS, performing actions and generating internal IDs.
    * **RabbitMQ Publisher:** Publishes responses back to the source system (e.g., `dms.response.1c.user_created`).
* **CRM Adapter (`CRMAdapter.py`):**
    * **RabbitMQ Consumer:** Listens to the `crm_queue` for requests (e.g., `update_order_status`) and responses (e.g., `policy_info_response` from DMS).
    * **Simulated Processing:** Simulates interactions with a real CRM, updating order statuses or processing policy information.
    * **RabbitMQ Publisher:** Publishes responses back to the source system (e.g., `crm.response.1c.order_status_updated`) and can initiate new requests to other systems (e.g., `crm.request.dms.get_policy_info`).
* **RabbitMQ (`rabbitmq:3-management-alpine`):**
    * The central message broker facilitating asynchronous communication between all adapters.
    * Configured with a `topic` exchange (`main_exchange`) for flexible routing.
    * Includes a management UI for monitoring queues, exchanges, and message flow.
* **Dead Letter Queues (DLQs):** Each adapter's queue (e.g., `1c_queue`, `dms_queue`, `crm_queue`) is configured with a corresponding Dead Letter Exchange (DLX) and Dead Letter Queue (DLQ). Messages that fail processing after a maximum number of retries, or are rejected/nacked without re-queueing, are automatically routed to these DLQs (e.g., `1c_dead_letter_queue`).

---

## Features

* **Asynchronous Messaging:** Utilizes RabbitMQ to enable decoupled communication between 1C, DMS, and CRM, enhancing system resilience and scalability.
* **Message Routing:** Employs a `topic` exchange with flexible routing keys (e.g., `source.request.target.message_type` or `source.response.target.message_type`) for precise message delivery.
* **Dead Letter Queues (DLQ):** Messages that fail processing (e.g., due to unhandled errors, invalid JSON) are automatically sent to dedicated dead-letter queues, ensuring no data loss and allowing for later investigation or reprocessing.
* **Retry Mechanism:** Adapters implement a basic retry mechanism (up to 3 attempts) before moving a message to its DLQ.
* **Containerized Environment:** All components are encapsulated in Docker containers, ensuring easy setup, portability, and consistent deployment across different environments.
* **Structured Logging:** Uses Python's `logging` module to provide clear and informative logs, aiding in debugging and monitoring.
* **HTTP Interface for 1C:** The `OneCAdapter.py` provides a Flask HTTP API, allowing 1C to easily integrate by making simple POST requests.

---

## Getting Started

### Prerequisites

Ensure you have **Docker** and **Docker Compose** installed.

### Running the Production Project

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/YourGitHubUsername/EnterpriseSystemIntegration.git](https://github.com/YourGitHubUsername/EnterpriseSystemIntegration.git) # Replace with your actual repo URL
    cd EnterpriseSystemIntegration
    ```

2.  **Create and configure the `.env` file:**
    In the root directory, create a `.env` file and configure the connection details for RabbitMQ and the **real CRM system**.

    ```
    # .env
    # RabbitMQ Connection Details
    RABBITMQ_HOST=rabbitmq
    RABBITMQ_PORT=5672
    RABBITMQ_USERNAME=guest
    RABBITMQ_PASSWORD=guest

    # 1C Adapter Details
    FLASK_PORT=5000

    # Real CRM System Connection Details
    CREATIO_URL=[https://your.real-creatio.com](https://your.real-creatio.com)
    CREATIO_AUTH_URL=/AuthService.svc/Login
    CREATIO_UPDATE_ORDER_URL=/odata/Order('{order_id}')
    CREATIO_USERNAME=your_real_crm_username
    CREATIO_PASSWORD=your_real_crm_password
    ```
    *Note: `RABBITMQ_HOST` is set to `rabbitmq` because that is the service name defined in `docker-compose.yml` for inter-container communication.*

3.  **Adjust the `docker-compose.yml` file:**
    You must remove the `fake_creatio` service from the `docker-compose.yml` file, as it is no longer needed. Update the `crm_adapter` service to reflect the real CRM's configuration.

    **Example `docker-compose.yml` (without `fake_creatio`):**
    ```yaml
    version: '3.8'

    services:
      rabbitmq:
        image: rabbitmq:3-management-alpine
        container_name: rabbitmq_broker
        ports:
          - "5672:5672"
          - "15672:15672"
        healthcheck:
          test: ["CMD", "rabbitmq-diagnostics", "check_port_connectivity"]
          interval: 10s
          timeout: 10s
          retries: 5

      crm_adapter:
        build:
          context: .
          dockerfile: Dockerfile_CRM
        container_name: crm_adapter_service
        env_file:
          - .env
        depends_on:
          rabbitmq:
            condition: service_healthy
        command: python CRMAdapter.py

      dms_adapter:
        build:
          context: .
          dockerfile: Dockerfile_DMS
        container_name: dms_adapter_service
        env_file:
          - .env
        depends_on:
          rabbitmq:
            condition: service_healthy
        command: python DMSAdapter.py

      ic_adapter:
        build:
          context: .
          dockerfile: Dockerfile_OneC
        container_name: ic_adapter_service
        ports:
          - "5000:5000"
        env_file:
          - .env
        depends_on:
          rabbitmq:
            condition: service_healthy
        command: python OneCAdapter.py
    ```

4.  **Build and run the services:**
    Navigate to the root directory of the project (where `docker-compose.yml` is located) in your terminal and run:

    ```bash
    docker compose down -v # Optional: Cleans up any previous runs, ensuring a fresh state
    docker compose up --build -d # Builds images and runs services in detached mode
    ```

    This command will:
    * Build Docker images for the 1C, DMS, and CRM adapters.
    * Start the RabbitMQ broker with its management UI.
    * Start all three adapter services, which will connect to RabbitMQ and the configured external systems.

5.  **Monitor the services:**
    * **View logs:** To view logs from all running services in real-time:
        ```bash
        docker compose logs -f
        ```
        To view logs from a specific service (e.g., 1C adapter):
        ```bash
        docker compose logs -f ic_adapter
        ```
        (Replace `ic_adapter` with `dms_adapter`, `crm_adapter`, or `rabbitmq` as needed.)

    * **RabbitMQ Management UI:** Open your web browser and navigate to [http://localhost:15672](http://localhost:15672) (default credentials: `guest`/`guest`).
        * Go to the "Queues" tab to observe message flow and accumulation in queues (e.g., `1c_queue`, `dms_queue`, `crm_queue`, and their corresponding `_dead_letter_queue`s).

### Testing the Integration

Once all services are running, you can test the communication flow. The `curl` commands remain the same, but the `crm_adapter` will now interact with your actual Creatio instance.

1.  **Send a `create_user` request from 1C to DMS:**
    ```bash
    curl -X POST -H "Content-Type: application/json" -d '{
        "request_id": "USER_REQ_001",
        "user_id": "U12345",
        "name": "Иванов Иван",
        "email": "ivanov@example.com"
    }' http://localhost:5000/send_to_dms
    ```
    * Observe the logs of `ic_adapter` (sending) and `dms_adapter` (receiving and processing).
    * Then, `ic_adapter` logs should show it receiving the `user_created_response` from DMS.

2.  **Send an `update_order_status` request from 1C to CRM:**

    ```bash
    curl -X POST -H "Content-Type: application/json" -d '{
        "request_id": "ORDER_REQ_002",
        "order_id": "ORD9876",
        "status": "Shipped",
        "needs_policy_info": true
    }' http://localhost:5000/send_to_crm
    ```
    * Observe the logs of `ic_adapter` (sending) and `crm_adapter` (receiving and processing).
    * The CRM adapter will now attempt to authenticate with and update the status in your real CRM system.
    * The CRM adapter might then send a request to the DMS adapter (`crm.request.dms.get_policy_info`), and the DMS adapter will respond.
    * Finally, `crm_adapter` will send an `order_status_updated_response` back to `ic_adapter`.

---

## Possible Improvements

* **Idempotency:** Implement idempotency keys in messages to ensure that a message can be processed multiple times (e.g., due to retries) without causing unintended side effects (e.g., creating duplicate entries or incorrect state changes).
* **Advanced Health Checks:** Implement more sophisticated health checks for adapter services that verify not only if the Flask app is running, but also if it can successfully connect to RabbitMQ and any other necessary external systems.
* **Message Schema Management:** While `json.loads` is used here, for complex integrations, consider a more robust schema registry and validation mechanism (e.g., Apache Avro, JSON Schema).
* **Error Handling Refinements:** Implement more granular error handling within `_process_message` functions to differentiate between transient errors (requeue with delay) and permanent errors (send to DLQ immediately).

---

## Project Background

This project was developed as part of an internship assignment focused on implementing a robust message broker solution for enterprise system communication (1C, CRM, DMS). 
It served as a hands-on exercise to gain practical experience with Python backend development, asynchronous messaging patterns, and building resilient distributed systems. 
This experience has significantly deepened my understanding of inter-system communication, data validation, and error handling in a real-world context.

---


Feel free to explore, modify, and expand this project! Contributions and feedback are welcome.
