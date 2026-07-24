import sqlalchemy
from sqlalchemy import create_engine, text, event
from uuid import uuid4, UUID
import os

engine = create_engine("sqlite:///:memory:")

@event.listens_for(engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    def convert_uuids(params):
        if isinstance(params, dict):
            for k, v in params.items():
                if isinstance(v, UUID):
                    params[k] = str(v)
                elif isinstance(v, dict) or isinstance(params[k], list):
                    convert_uuids(v)
        elif isinstance(params, list):
            for i, v in enumerate(params):
                if isinstance(v, UUID):
                    params[i] = str(v)
                elif isinstance(v, dict) or isinstance(params[i], list):
                    convert_uuids(v)
    if parameters:
        convert_uuids(parameters)

# Test execution:
with engine.connect() as conn:
    conn.execute(text("CREATE TABLE test (id TEXT PRIMARY KEY)"))
    uid = uuid4()
    conn.execute(text("INSERT INTO test (id) VALUES (:id)"), {"id": uid})
    conn.commit()
    
    res = conn.execute(text("SELECT id FROM test")).fetchall()
    print("Result:", res)
    print("Matches UUID:", UUID(res[0][0]) == uid)
