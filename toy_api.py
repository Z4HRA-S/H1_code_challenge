import asyncio
import random

import uvicorn
import yaml
from fastapi import FastAPI, Response
from pydantic import BaseModel


class Group(BaseModel):
    groupId: str


def create_app():
    app = FastAPI()

    def random_status(*success_codes):
        if random.random() < 0.7:
            return random.choice(success_codes)

        return random.choice([500, 502, 503, 504])

    @app.post("/v1/group/")
    async def create_group(group: Group):
        return Response(status_code=random_status(201))

    @app.delete("/v1/group/")
    async def delete_group(group: Group):
        return Response(status_code=random_status(200))

    @app.get("/v1/group/{group_id}/")
    async def get_group(group_id: str):
        return Response(status_code=random_status(200, 404))

    return app


def load_config(path="config.yaml"):
    with open(path) as file:
        return yaml.safe_load(file)


async def run_node(host, port):
    config = uvicorn.Config(
        create_app(),
        host=host,
        port=port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    config = load_config()

    tasks = []

    for node in config["nodes"]:
        host, port = node.rsplit(":", 1)
        tasks.append(run_node(host, int(port)))

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())