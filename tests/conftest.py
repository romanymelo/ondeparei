import pytest
from fastapi.testclient import TestClient

from tests.fakes import FakeCatalog, make_detail, make_page


@pytest.fixture
def make_client(tmp_path):
    from app.main import create_app

    clients = []

    def _make(fake, db=None):
        client = TestClient(create_app(catalog=fake, database_path=db or tmp_path / "catalogo.db"))
        client.__enter__()
        clients.append(client)
        return client

    yield _make
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def fake():
    return FakeCatalog(discover=make_page(), search=make_page(), detail=make_detail())


@pytest.fixture
def client(make_client, fake):
    return make_client(fake)
