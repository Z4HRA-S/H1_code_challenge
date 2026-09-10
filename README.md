# Assumptions & Design Notes

## Assumptions

* A cluster consists of multiple independent nodes, all exposing the same Group REST API.
* Each node can contain multiple groups.
* A group is identified by its `groupId`.
* The term "object" in the task refers to the Group resource; no separate object entity is assumed.
* A cluster-level create is considered successful only when the group is successfully created on all nodes. The same applies to delete.
* Operations on the same `groupId` are assumed not to be concurrently modified by independent clients.
* The cluster API itself is outside the scope of this project and is therefore mocked in unit tests.

## Design Notes

### Consistency and Atomicity

The client cannot provide strict atomicity across nodes because the provided API does not expose a distributed transaction or commit protocol.

Temporary inconsistency between nodes is therefore unavoidable while an operation is in progress. The client aims to minimize this window and restore the desired state as reliably as possible.

### Failure Handling

Network failures, timeouts, and server-side errors are expected. Transient failures are handled using bounded retries with backoff.

A timeout or connection failure does not necessarily mean that the operation was not applied. The request may have reached the server while its response was lost. Such ambiguous outcomes are reconciled using the `GET` endpoint before taking compensating action.

### Compensation

Rollback is implemented as a **state-aware compensating transaction**, rather than blindly executing the inverse HTTP operation.

For example, after an uncertain `POST`, the client first determines whether the group actually exists before deciding whether a compensating `DELETE` is required.

Compensation itself may fail, so it is also subject to retry and error reporting.

### Guarantees and Limitations

The client guarantees that it reports an operation as successful only after all nodes have reached the desired state.

It does **not** guarantee atomic visibility: another consumer may observe an intermediate state while the operation is being executed.

Because the API provides no distributed transaction, locking, versioning, or durable operation state, the client cannot guarantee recovery from every possible failure scenario, particularly if the client terminates while an operation or its compensation is in progress.
