# API Consumer

A Python client for performing Group create/delete operations across multiple API nodes while handling partial failures, ambiguous responses, rollback, and recovery of unresolved operations.

## Components

### `client.py`

Contains the `GroupOperation` client.

It sends Group operations concurrently to all configured nodes, evaluates the result of each node, and performs state-aware compensation when an operation fails. For ambiguous failures, such as a server error or lost response, the client uses the `GET` endpoint to determine the current state before deciding whether compensation is required.

### `main.py`

Coordinates the client and the database.

It registers nodes, manages group versions, persists operation results, and identifies operations that remain unresolved. It also provides a recovery flow for operations that could not be resolved during the original execution.

### `toy_api.py`

Provides a simple stateless FastAPI implementation of the required Group API for local testing.

The API intentionally returns randomized success and failure responses to simulate an unstable external API. It does not maintain group state or use a database.

## Assumptions

- A cluster consists of multiple independent nodes exposing the same Group REST API.
- Each node can contain multiple groups.
- A group is identified by its `groupId`.
- The term "object" in the task refers to the Group resource; no separate object entity is assumed.
- A cluster-level create/delete is considered successful only when all nodes reach the desired state.
- Operations on the same `groupId` are assumed not to be concurrently modified by independent clients.
- The API itself is outside the scope of this project and is mocked in unit tests.
- The configured node addresses are reachable from the environment where the client runs.



## Limitations



### Consistency and Atomicity

The client cannot provide strict atomicity across nodes because the API does not expose a distributed transaction or commit protocol.

Temporary inconsistency between nodes is therefore possible while an operation is in progress.

The client only reports a successful cluster-level operation after all nodes have reached the desired state.

### Ambiguous Failures

A failed HTTP request does not necessarily mean that the operation was not applied. The request may have reached the server while its response was lost.

The client therefore uses `GET` to reconcile the state before performing a compensating operation.

If the state cannot be determined, the node remains `unknown` and the operation can require later recovery.

### Recovery

If an operation cannot be resolved during the original execution, its unresolved node operations are persisted and can be processed by the recovery flow.

The current implementation runs recovery as part of the application flow. In a production deployment, recovery should be separated into a scheduled/recurring process, such as a Kubernetes CronJob.

### Persistence and Architecture

The database is currently created and accessed directly by the application for simplicity.

In a production architecture, database access should be provided through dependency injection rather than being created inside the application flow.

Database credentials and other environment-specific settings should also be provided through external configuration or Kubernetes Secrets rather than being kept in application configuration.


## Design Inspiration

The compensation and recovery design was inspired by the [Saga pattern](https://www.tothenew.com/blog/distributed-transactions-in-microservices-how-the-saga-pattern-solves-real-problems/), particularly the idea of using compensating operations instead of relying on distributed transactions.

The implementation was adapted to the requirements of this assignment. Since each node performs the same operation independently, node operations are treated as independent tasks and are executed in parallel rather than as a sequential chain of business transactions.

If an operation succeeds on some nodes but fails on others, successful nodes are compensated by applying the inverse operation. In addition, a separate recovery mechanism is provided for cases where the compensation itself fails. Unresolved node operations are persisted as `UNKNOWN` and can be retried later by the recovery flow.

Therefore, the implementation follows the compensation principle of the Saga pattern, while adapting it to a parallel multi-node operation rather than a sequence of distributed business transactions.



### Configuration

Configure the API nodes and requested operations in `config.yaml`:

```yaml
nodes:
  - node1:8000
  - node2:8000
  - node3:8000

operations:
  - operation: create
    group_name: customers

  - operation: create
    group_name: orders

  - operation: delete
    group_name: customers
```

The node addresses must be reachable from the client environment.

### Run locally

Install the dependencies:

```bash
pip install -r requirements.txt
```

Then run:

```bash
python main.py
```



### Run with the Toy API

If no external API is available, the included `toy_api.py` can be used for local testing.

For the Docker setup, remove the normal `main.py` command from the Kubernetes Job and uncomment the Toy API command in the `Dockerfile`:

```dockerfile
# CMD ["sh", "-c", "python toy_api.py & sleep 2"]
```

The Toy API starts the configured local nodes first, waits briefly for them to become available, and then runs the client.

### Kubernetes / Minikube
Run:

```bash
./run_k8s.sh
```

The configured API nodes must be reachable from the Kubernetes cluster.

## Deliberately Simplified Design

Several parts of the implementation are intentionally kept simple for the scope of this assignment:

- Recovery is implemented as an application flow rather than a scheduled Kubernetes CronJob.
- Database access is not dependency-injected.
- Database credentials and environment-specific configuration are not handled through a dedicated secrets/configuration system.
- The API implementation is not part of the project; `toy_api.py` is only a lightweight local testing utility.
- Kubernetes deployment is limited to a basic Job and ConfigMap rather than a complete production deployment setup.
- Unit tests mock the external API instead of running an end-to-end cluster.

## AI Assistance

AI tools were used during this assignment:

* **Code:** I provided detailed instructions for the specific functions and logic to implement. I personally debugged, reviewed, and edited the code line by line. The commit history reflects this process. I did not use an agent to independently generate the entire repository, and I did not blindly accept AI-generated suggestions.
* **Research:** AI was used to make web research faster and more targeted. For specific questions, I asked it to search or crawl particular websites and summarize the relevant findings.
* **README:** I provided detailed instructions about the structure and content of the README and used AI to help turn those instructions into the final documentation.

The complete AI conversation used during this assignment is also available upon request.
