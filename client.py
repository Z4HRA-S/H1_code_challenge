import asyncio
import httpx


class GroupOperation:
    def __init__(self, group_id):
        self.group_id = group_id

        self.state = {
            "operation": None,
            "operation_result": [],
            "rollback": None,
            "rollback_result": [],
            "overall_state": None,
        }

    async def send_request(self, method, node):
        async with httpx.AsyncClient() as client:
            if method == "create":
                response = await client.post(
                    f"{node}/v1/group/",
                    json={"groupId": self.group_id},
                )

            elif method == "delete":
                response = await client.delete(
                    f"{node}/v1/group/",
                    json={"groupId": self.group_id},
                )

            elif method == "get":
                response = await client.get(
                    f"{node}/v1/group/{self.group_id}/",
                )

            return response

    async def process(self, method, node, response):
        if method == "create":
            if response.status_code == 201:
                return {
                    "node": node,
                    "state": "created",
                    "success": True,
                }

            get_response = await self.send_request("get", node)

            if get_response.status_code == 404:
                state = "not_created"
            elif get_response.status_code == 200:
                state = "created"

            else:
                state = "unknown"

            return {
                "node": node,
                "state": state,
                "success": True if state=="created" else False,
            }

        if method == "delete":
            if response.status_code == 200:
                return {
                    "node": node,
                    "state": "deleted",
                    "success": True,
                }

            get_response = await self.send_request("get", node)

            if get_response.status_code == 404:
                state = "deleted"
            elif get_response.status_code == 200:
                state = "not_deleted"
            else:
                state = "unknown"

            return {
                "node": node,
                "state": state,
                "success": True if state=="deleted" else False,
            }

        return {
            "node": node,
            "state": "unknown",
            "success": False,
        }


    async def run(self, operation, nodes):
        self.state["operation"] = operation

        tasks = [asyncio.create_task(self.send_request(operation, node))
            for node in nodes
        ]

        results = []

        for task in asyncio.as_completed(tasks):
            node, response = await task
            result = await self.process(operation, node, response)
            results.append(result)

        self.state["operation_result"] = results

        success = all(r["success"] for r in results)

        self.state["overall_state"] = (
            "success" if success else "fail"
        )

        if not success:
            nodes_to_rollback = [ r["node"] for r in results if r["success"]] # rollback successful ones
            rollback_result = await self.rollback(operation, nodes_to_rollback)
            self.state["rollback_result"] = rollback_result
            rollback_success = all(r["success"] for r in rollback_result)
            self.state["rollback"] = success

        return self.state


    async def rollback(self, operation, nodes):
        rollback_operation = "delete" if operation == "create" else "create"
        self.state["rollback"] = rollback_operation
        tasks = [asyncio.create_task(self.send_request(rollback_operation, node))
                    for node in nodes]

        results = []

        for task in asyncio.as_completed(tasks):
            node, response = await task
            result = await self.process(rollback_operation, node, response)
            results.append(result)

        return results