from pathlib import Path

from ariadne import load_schema_from_path, make_executable_schema

from .types import types

HERE = Path(__file__).parent

type_defs = load_schema_from_path(str(HERE / "schema.graphql"))

schema = make_executable_schema(type_defs, types)  # type: ignore
