import pytest

import db as db_module


@pytest.fixture
def conn():
    connection = db_module.connect(":memory:")
    yield connection
    connection.close()
