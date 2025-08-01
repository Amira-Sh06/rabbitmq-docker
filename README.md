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
├── RabbitMQ.py          # Reusable RabbitMQ client class
├── README.md            # This file
└── requirements.txt     # Python dependencies
```

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

### Running the Project

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/YourGitHubUsername/EnterpriseSystemIntegration.git](https://github.com/YourGitHubUsername/EnterpriseSystemIntegration.git) # Replace with your actual repo URL
    cd EnterpriseSystemIntegration
    ```

2.  **Create a `.env` file:**
    In the root directory, create a `.env` file and populate it with RabbitMQ connection details and the Flask port. These values are used by `RabbitMQ.py` and `OneCAdapter.py`.

    ```
    # .env
    RABBITMQ_HOST=rabbitmq
    RABBITMQ_PORT=5672
    RABBITMQ_USERNAME=guest
    RABBITMQ_PASSWORD=guest
    FLASK_PORT=5000
    ```
    *Note: `RABBITMQ_HOST` is set to `rabbitmq` because that is the service name defined in `docker-compose.yml` for inter-container communication.*

3.  **Build and run the services:**
    Navigate to the root directory of the project (where `docker-compose.yml` is located) in your terminal and run:

    ```bash
    docker compose down -v # Optional: Cleans up any previous runs, ensuring a fresh state
    docker compose up --build -d # Builds images and runs services in detached mode
    ```

    This command will:
    * Build Docker images for the 1C, DMS, and CRM adapters.
    * Start the RabbitMQ broker with its management UI.
    * Start all three adapter services, which will connect to RabbitMQ.

4.  **Monitor the services:**
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

Once all services are running, you can test the communication flow:

1.  **Send a `create_user` request from 1C to DMS:**
    You can use `curl` or Postman/Insomnia to send a POST request to the 1C adapter's Flask endpoint.

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
    * The CRM adapter might then send a request to the DMS adapter (`crm.request.dms.get_policy_info`), and the DMS adapter will respond.
    * Finally, `crm_adapter` will send an `order_status_updated_response` back to `ic_adapter`.

---

## How it Works

1.  **Message Flow:**
    * **1C Initiates:** The 1C system (simulated by HTTP requests to `OneCAdapter.py`) sends JSON payloads to `/send_to_dms` or `/send_to_crm`.
    * **1C Adapter Publishes:** `OneCAdapter.py` transforms these HTTP requests into structured messages and publishes them to the `main_exchange` in RabbitMQ with a specific `routing_key` (e.g., `1c.request.dms.create_user`).
    * **Target Adapters Consume:** The `DMSAdapter` and `CRMAdapter` are subscribed to queues (`dms_queue`, `crm_queue`) that are bound to the `main_exchange` with wildcards (`*.request.dms.#`, `*.request.crm.#`), allowing them to receive relevant messages.
    * **Processing and Response:** Upon receiving a message, the target adapter processes it (simulating interaction with the actual business system). After processing, it publishes a response message back to the `main_exchange` with a routing key targeting the source system (e.g., `dms.response.1c.user_created`).
    * **1C Adapter Consumes Responses:** `OneCAdapter.py` also runs a consumer thread (`ICListener`) that listens for messages on the `1c_queue`, which is bound to receive responses from DMS (`dms.response.1c.#`) and CRM (`crm.response.1c.#`). These responses can then be used to update 1C's internal state.

2.  **Dead Letter Queues (DLQs):**
    * Each primary queue (e.g., `1c_queue`, `dms_queue`, `crm_queue`) has a Dead Letter Exchange (DLX) and a corresponding Dead Letter Queue (DLQ) configured (e.g., `1c_dead_letter_queue`).
    * If a message consumer fails to process a message (e.g., due to an exception during `_process_message`) and explicitly `nack`s it with `requeue=False`, or if the message reaches its maximum retry limit, it will be routed to its respective DLQ.
    * This ensures that no messages are lost due to processing failures and provides a mechanism for manual inspection and reprocessing of problematic messages.

---

## Future Enhancements

This project serves as a solid foundation, but for a production-grade enterprise integration solution, several key areas can be enhanced:

* **Delayed Retries:** Implement exponential backoff for retries using RabbitMQ's `rabbitmq_delayed_message_exchange` plugin. This allows messages to be re-queued with a delay, preventing a "thundering herd" problem on services that are temporarily failing.
* **Circuit Breakers:** Implement circuit breaker patterns within the adapters, especially when they communicate with external (simulated) APIs. This prevents repeated calls to services that are known to be failing, preserving system resources and improving overall resilience.
* **Monitoring and Alerting:**
    * Integrate with dedicated monitoring tools like **Prometheus** for metrics collection (e.g., message rates, error rates, consumer lag).
    * Use **Grafana** for dashboarding to visualize RabbitMQ performance and adapter health.
    * Set up alerts for critical issues (e.g., high number of messages in DLQs, adapter crashes, high error rates from external APIs).
* **Authentication and Authorization:**
    * Secure RabbitMQ connections with robust user roles and **SSL/TLS**.
    * Secure the Flask API endpoints in `OneCAdapter.py` with **API keys**, **OAuth2**, or other strong authentication methods to control access from 1C.
* **Scalability:**
    * For higher message loads, consider running multiple instances of each adapter service. Docker Compose can easily scale services (`docker compose up --scale crm_adapter=3`).
    * For extreme loads or high availability, a **RabbitMQ cluster** might be necessary.
* **Configuration Management:** For complex production deployments, move beyond `.env` files to more sophisticated configuration management solutions (e.g., Kubernetes ConfigMaps, HashiCorp Vault for secrets, or dedicated configuration services).
* **Idempotency:** Design all message processing logic to be **idempotent**. This means that an operation can be safely repeated multiple times (e.g., due to retries) without causing unintended side effects (e.g., creating duplicate entries or incorrect state changes).
* **Advanced Health Checks:** Implement more sophisticated health checks for adapter services that verify not only if the Flask app is running, but also if it can successfully connect to RabbitMQ and any other necessary external systems.
* **Message Schema Management:** While `json.loads` is used here, for complex integrations, consider a more robust schema registry and validation mechanism (e.g., Apache Avro, JSON Schema outside of just Pydantic models for cross-language compatibility).
* **Error Handling Refinements:** Implement more granular error handling within `_process_message` functions to differentiate between transient errors (requeue with delay) and permanent errors (send to DLQ immediately).

---

## Project Background

This project was developed as part of an internship assignment focused on implementing a robust message broker solution for enterprise system communication (1C, CRM, DMS). 
It served as a hands-on exercise to gain practical experience with Python backend development, asynchronous messaging patterns, and building resilient distributed systems. 
This experience has significantly deepened my understanding of inter-system communication, data validation, and error handling in a real-world context.

---

Feel free to explore, modify, and expand this project! Contributions and feedback are welcome.