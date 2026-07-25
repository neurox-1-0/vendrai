import os
import uuid
from typing import TypedDict

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from psycopg import AsyncConnection
from psycopg.rows import dict_row

pytestmark = pytest.mark.skipif(
    not os.getenv("NEUROX_LIVE_POSTGRES_URL"),
    reason="requires the opt-in live PostgreSQL test database",
)


class State(TypedDict, total=False):
    value: str
    response: str


def _graph(saver):
    def gate(_state: State) -> State:
        return {"response": str(interrupt({"kind": "TEST_APPROVAL"}))}

    builder = StateGraph(State)
    builder.add_node("gate", gate)
    builder.add_edge(START, "gate")
    builder.add_edge("gate", END)
    return builder.compile(checkpointer=saver)


async def _connection(url: str, tenant_id: str):
    connection = await AsyncConnection.connect(
        url,
        autocommit=True,
        prepare_threshold=0,
        row_factory=dict_row,
    )
    await connection.execute(
        "SELECT set_config('app.current_tenant_id', %s, false)",
        (tenant_id,),
    )
    return connection


@pytest.mark.asyncio
async def test_checkpoint_survives_connection_restart_and_is_tenant_scoped():
    url = os.environ["NEUROX_LIVE_POSTGRES_URL"]
    tenant_a = "00000000-0000-0000-0000-000000000001"
    tenant_b = "00000000-0000-0000-0000-000000000002"
    thread_id = f"{tenant_a}:test:{uuid.uuid4()}"
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}

    first_connection = await _connection(url, tenant_a)
    try:
        first = await _graph(
            AsyncPostgresSaver(first_connection)
        ).ainvoke({"value": "persisted"}, config)
        assert first["__interrupt__"][0].value["kind"] == "TEST_APPROVAL"
    finally:
        await first_connection.close()

    second_connection = await _connection(url, tenant_a)
    try:
        resumed = await _graph(
            AsyncPostgresSaver(second_connection)
        ).ainvoke(Command(resume="approved"), config)
        assert resumed == {"value": "persisted", "response": "approved"}
    finally:
        await second_connection.close()

    other_tenant_connection = await _connection(url, tenant_b)
    try:
        hidden = await AsyncPostgresSaver(
            other_tenant_connection
        ).aget_tuple(config)
        assert hidden is None
    finally:
        await other_tenant_connection.close()
